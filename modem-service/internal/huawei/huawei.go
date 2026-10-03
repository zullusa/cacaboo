// Package huawei drives the HTTP API of a Huawei E3372 (Hilink firmware) that
// runs in NDIS mode. Unlike the Keenetic router — which fronts a modem with its
// own NDM/RCI API — the modem here *is* the web server (192.168.8.1 by default)
// and needs no login, but it guards every call with a CSRF token that it rotates
// after each answered request. See HUAWEI_API.md for the probed details.
package huawei

import (
	"context"
	"encoding/xml"
	"errors"
	"fmt"
	"io"
	"log"
	"net/http"
	"regexp"
	"strings"
	"sync"
	"time"
	"unicode/utf8"

	"modem-service/internal/modem"
)

const (
	// indexPath is the WebUI entry point. Fetching it hands out both the
	// session cookie and the CSRF token every /api/... call needs.
	indexPath = "/html/index.html"

	// tokenHeader carries the CSRF token in both directions: the client sends
	// the current value, the modem answers with the next one.
	tokenHeader = "__RequestVerificationToken"

	// contentType is what the modem's own WebUI posts its XML payload with. The
	// body is raw XML, it is *not* URL-encoded despite the content type.
	contentType = "application/x-www-form-urlencoded; charset=UTF-8"

	// The SMS endpoints of the modem.
	smsPathSend   = "/api/sms/send-sms"
	smsPathList   = "/api/sms/sms-list"
	smsPathDelete = "/api/sms/delete-sms"
	smsPathCount  = "/api/sms/sms-count"

	// boxLocalInbox is the BoxType of the modem's own inbox (the SIM card holds
	// at most SimMax entries, so only the local store is of any use).
	boxLocalInbox = 1
)

// Message types reported by the modem. Everything below 7 is an ordinary
// incoming/outgoing message; 7 and 8 are the operator's delivery receipts for a
// message we sent, stored in the same inbox (see HUAWEI_API.md).
const (
	smsTypeReportDelivered = 7
	smsTypeReportFailed    = 8
)

// Modem error codes worth reacting to.
const (
	errCodeWrongToken   = "125001"
	errCodeWrongSession = "125002"
	errCodeStaleToken   = "125003"
)

const dateLayout = "2006-01-02 15:04:05"

var (
	indexTokenPattern  = regexp.MustCompile(`name="csrf_token"\s+content="([^"]+)"`)
	indexSessionRegexp = regexp.MustCompile(`(?i)\bSessionID=([^;]+)`)
)

// Options configures a Client. Only BaseURL is required; the remaining values
// mirror the modem-service defaults (see config.Load).
type Options struct {
	// BaseURL is the modem's web server root, e.g. http://192.168.8.1.
	BaseURL string
	// HTTPTimeout bounds a single HTTP call. Zero means 30s.
	HTTPTimeout time.Duration
	// PageSize is the ReadCount of one sms-list page. Zero means 20.
	PageSize int
	// MaxPages bounds how many pages a single ListInbox walks. Zero means 5.
	MaxPages int
	// ReportTimeout is how long Send waits for the operator's delivery receipt.
	// Zero (the default) makes Send return as soon as the modem accepted the
	// message; a receipt that never arrives is never treated as a failure.
	ReportTimeout time.Duration
	// ReportPollInterval is the delay between two receipt lookups. Zero means 5s.
	ReportPollInterval time.Duration
	// Now overrides the clock (tests). It also fills the <Date> field.
	Now func() time.Time
}

// Client talks to a Huawei E3372 web API. It is safe for concurrent use: the
// session cookie and the rotating CSRF token are guarded by a mutex, because a
// token is only valid for the single call it was issued for.
type Client struct {
	baseURL    string
	httpClient *http.Client
	pageSize   int
	maxPages   int
	reportWait time.Duration
	reportPoll time.Duration
	now        func() time.Time

	mu      sync.Mutex
	session string
	token   string

	// reportIDs holds the inbox ids already consumed as the delivery receipt of
	// one of our sends, so they are never reported as new messages.
	reportsMu sync.Mutex
	reportIDs map[string]bool
}

// compile-time proof that the client satisfies both worker and poller contracts.
var (
	_ modem.Sender = (*Client)(nil)
	_ modem.Inbox  = (*Client)(nil)
)

// New builds a Client for the given options.
func New(opts Options) *Client {
	timeout := opts.HTTPTimeout
	if timeout <= 0 {
		timeout = 30 * time.Second
	}
	pageSize := opts.PageSize
	if pageSize <= 0 {
		pageSize = 20
	}
	maxPages := opts.MaxPages
	if maxPages <= 0 {
		maxPages = 5
	}
	reportPoll := opts.ReportPollInterval
	if reportPoll <= 0 {
		reportPoll = 5 * time.Second
	}
	now := opts.Now
	if now == nil {
		now = time.Now
	}
	return &Client{
		baseURL:    strings.TrimRight(opts.BaseURL, "/"),
		httpClient: &http.Client{Timeout: timeout},
		pageSize:   pageSize,
		maxPages:   maxPages,
		reportWait: opts.ReportTimeout,
		reportPoll: reportPoll,
		now:        now,
		reportIDs:  make(map[string]bool),
	}
}

// Send hands one SMS to the modem. When ReportTimeout is configured it then
// waits for the operator's delivery receipt and fails the send only when the
// receipt explicitly reports a failure — a receipt that never arrives is logged
// and otherwise ignored, so a delayed receipt cannot cause a duplicate SMS.
func (c *Client) Send(ctx context.Context, phone, text string) error {
	phone = strings.TrimSpace(phone)
	text = strings.TrimSpace(text)
	if phone == "" {
		return errors.New("huawei: empty phone number")
	}
	if text == "" {
		return errors.New("huawei: empty message text")
	}

	// Snapshot the receipts the modem already holds: the ones appearing after
	// this point belong to this send. Comparing ids keeps the match independent
	// of the modem's minute-resolution timestamps.
	known := c.reportIDsFor(ctx, phone)

	payload, err := buildXML(sendRequest{
		Index:    "-1",
		Phones:   []string{phone},
		Content:  text,
		Length:   utf8.RuneCountInString(text),
		Reserved: "0",
		Date:     c.now().Format(dateLayout),
	})
	if err != nil {
		return err
	}

	body, err := c.post(ctx, smsPathSend, payload)
	if err != nil {
		return err
	}
	if err := expectOK(body); err != nil {
		return fmt.Errorf("huawei: send-sms refused the message to %s: %w", phone, err)
	}

	if c.reportWait <= 0 {
		return nil
	}
	return c.awaitReport(ctx, phone, known)
}

// awaitReport polls the inbox until the delivery receipt of a just sent message
// appears. SmsType 7 means delivered, 8 means the network refused it.
func (c *Client) awaitReport(ctx context.Context, phone string, known map[string]bool) error {
	deadline := c.now().Add(c.reportWait)
	for {
		entry, found, err := c.findNewReport(ctx, phone, known)
		if err != nil {
			// The message itself was accepted, so a failing receipt lookup must
			// not turn into a retry of an already sent SMS.
			logf("delivery receipt lookup for %s failed, continuing without it: %v", phone, err)
			return nil
		}
		if found {
			known[entry.Index] = true
			// Free the inbox slot: the receipt was used, nobody else needs it.
			if err := c.DeleteSMS(ctx, entry.Index); err != nil {
				logf("could not delete the delivery receipt %s from the modem: %v", entry.Index, err)
			}
			if atoi(entry.SmsType) == smsTypeReportFailed {
				return fmt.Errorf("huawei: the operator reported a failed delivery to %s", phone)
			}
			return nil
		}
		if !c.now().Before(deadline) {
			logf(
				"no delivery receipt for %s within %s, the modem accepted the message anyway",
				phone, c.reportWait,
			)
			return nil
		}

		timer := time.NewTimer(c.reportPoll)
		select {
		case <-ctx.Done():
			timer.Stop()
			return ctx.Err()
		case <-timer.C:
		}
	}
}

// findNewReport returns the first delivery receipt for phone that is not in
// known, i.e. a receipt produced after the send started.
func (c *Client) findNewReport(ctx context.Context, phone string, known map[string]bool) (messageEntry, bool, error) {
	entries, err := c.listEntries(ctx)
	if err != nil {
		return messageEntry{}, false, err
	}
	for _, entry := range entries {
		if known[entry.Index] || !entry.isReport() || entry.Phone != phone {
			continue
		}
		return entry, true, nil
	}
	return messageEntry{}, false, nil
}

// reportIDsFor collects the ids of the receipts the modem currently holds for a
// phone. A failing lookup is not fatal: an incomplete snapshot only means the
// wait may pick up a receipt of an earlier send.
func (c *Client) reportIDsFor(ctx context.Context, phone string) map[string]bool {
	ids := make(map[string]bool)
	entries, err := c.listEntries(ctx)
	if err != nil {
		logf("could not snapshot the delivery receipts before sending to %s: %v", phone, err)
		return ids
	}
	for _, entry := range entries {
		if entry.isReport() && entry.Phone == phone {
			ids[entry.Index] = true
		}
	}
	return ids
}

// ListInbox returns the messages stored in the modem's local inbox, newest
// first, walking up to MaxPages pages of PageSize entries.
func (c *Client) ListInbox(ctx context.Context) ([]modem.IncomingSMS, error) {
	entries, err := c.listEntries(ctx)
	if err != nil {
		return nil, err
	}
	messages := make([]modem.IncomingSMS, 0, len(entries))
	for _, entry := range entries {
		if c.consumedReport(entry.Index) {
			continue
		}
		messages = append(messages, entry.incoming())
	}
	return messages, nil
}

// DeleteSMS removes a message from the modem by its local id (ListInbox).
func (c *Client) DeleteSMS(ctx context.Context, id string) error {
	payload, err := buildXML(indexRequest{Index: id})
	if err != nil {
		return err
	}
	body, err := c.post(ctx, smsPathDelete, payload)
	if err != nil {
		return err
	}
	if err := expectOK(body); err != nil {
		return fmt.Errorf("huawei: delete-sms refused the index %s: %w", id, err)
	}
	return nil
}

// Count holds how many messages the modem stores per box.
type Count struct {
	LocalUnread  int
	LocalInbox   int
	LocalOutbox  int
	LocalDraft   int
	LocalDeleted int
	SimInbox     int
	NewMessages  int
}

// GetCount reads the modem's message counters (used by diagnostics).
func (c *Client) GetCount(ctx context.Context) (Count, error) {
	body, err := c.get(ctx, smsPathCount)
	if err != nil {
		return Count{}, err
	}
	var response countResponse
	if err := xml.Unmarshal(body, &response); err != nil {
		return Count{}, fmt.Errorf("huawei: cannot parse the modem counters: %w", err)
	}
	return Count{
		LocalUnread:  response.LocalUnread,
		LocalInbox:   response.LocalInbox,
		LocalOutbox:  response.LocalOutbox,
		LocalDraft:   response.LocalDraft,
		LocalDeleted: response.LocalDeleted,
		SimInbox:     response.SimInbox,
		NewMessages:  response.NewMessages,
	}, nil
}

// consumedReport reports whether a delivery receipt was already used to confirm
// one of our sends.
func (c *Client) consumedReport(id string) bool {
	c.reportsMu.Lock()
	defer c.reportsMu.Unlock()
	return c.reportIDs[id]
}

// listEntries reads every page of the modem inbox.
func (c *Client) listEntries(ctx context.Context) ([]messageEntry, error) {
	var entries []messageEntry
	for page := 1; page <= c.maxPages; page++ {
		payload, err := buildXML(listRequest{
			PageIndex:       page,
			ReadCount:       c.pageSize,
			BoxType:         boxLocalInbox,
			SortType:        0,
			Ascending:       0,
			UnreadPreferred: 0,
		})
		if err != nil {
			return nil, err
		}

		body, err := c.post(ctx, smsPathList, payload)
		if err != nil {
			return nil, err
		}
		var response listResponse
		if err := xml.Unmarshal(body, &response); err != nil {
			return nil, fmt.Errorf("huawei: cannot parse the modem inbox: %w", err)
		}
		if len(response.Messages) == 0 {
			break
		}
		entries = append(entries, response.Messages...)
		if len(response.Messages) < c.pageSize {
			break
		}
	}
	return entries, nil
}

// post sends an XML payload to a modem endpoint.
func (c *Client) post(ctx context.Context, path, payload string) ([]byte, error) {
	return c.call(ctx, http.MethodPost, path, payload)
}

// get reads a modem endpoint that needs no payload.
func (c *Client) get(ctx context.Context, path string) ([]byte, error) {
	return c.call(ctx, http.MethodGet, path, "")
}

// call performs one API call, bootstrapping the session when needed. The session
// cookie and the CSRF token are shared state, so calls are serialized.
func (c *Client) call(ctx context.Context, method, path, payload string) ([]byte, error) {
	c.mu.Lock()
	defer c.mu.Unlock()

	var lastErr error
	// Two attempts are enough: the first one may meet a token the modem has
	// already retired, the second one starts from a fresh session.
	for attempt := 0; attempt < 2; attempt++ {
		if err := c.bootstrap(ctx); err != nil {
			return nil, err
		}

		var reader io.Reader
		if payload != "" {
			reader = strings.NewReader(payload)
		}
		req, err := http.NewRequestWithContext(ctx, method, c.baseURL+path, reader)
		if err != nil {
			return nil, err
		}
		req.Header.Set(tokenHeader, c.token)
		req.Header.Set("Accept", "text/html, application/xml, */*")
		if payload != "" {
			req.Header.Set("Content-Type", contentType)
		}
		if c.session != "" {
			req.Header.Set("Cookie", "SessionID="+c.session)
		}

		resp, err := c.httpClient.Do(req)
		if err != nil {
			return nil, fmt.Errorf("huawei: %s %s: %w", method, path, err)
		}
		body, readErr := io.ReadAll(resp.Body)
		resp.Body.Close()

		// Pick up the rotated token before anything else — including before
		// deciding to retry, since the retry needs the fresh one.
		if rotated := resp.Header.Get(tokenHeader); rotated != "" {
			c.token = rotated
		}
		if readErr != nil {
			return nil, fmt.Errorf("huawei: %s %s: cannot read the reply: %w", method, path, readErr)
		}
		if resp.StatusCode != http.StatusOK {
			return nil, fmt.Errorf(
				"huawei: %s %s: http %d: %s", method, path, resp.StatusCode, truncate(string(body)),
			)
		}
		if err := apiError(body); err != nil {
			if isSessionError(err) {
				// 125001/125002/125003 all mean "start a new session": drop what
				// we hold so bootstrap() runs again on the next attempt.
				c.session, c.token = "", ""
				lastErr = err
				continue
			}
			return nil, fmt.Errorf("huawei: %s %s: %w", method, path, err)
		}
		return body, nil
	}
	return nil, fmt.Errorf("huawei: %s %s: still failing after a new session: %w", method, path, lastErr)
}

// bootstrap fetches the WebUI entry point to obtain a session cookie and a CSRF
// token. It is a no-op once both are held.
func (c *Client) bootstrap(ctx context.Context) error {
	if c.session != "" && c.token != "" {
		return nil
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.baseURL+indexPath, nil)
	if err != nil {
		return err
	}
	req.Header.Set("Accept", "text/html")

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("huawei: cannot reach the modem web UI at %s: %w", c.baseURL+indexPath, err)
	}
	body, readErr := io.ReadAll(resp.Body)
	resp.Body.Close()
	if readErr != nil {
		return fmt.Errorf("huawei: cannot read the modem web UI: %w", readErr)
	}
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("huawei: the modem web UI answered http %d", resp.StatusCode)
	}

	token := firstSubmatch(indexTokenPattern, string(body))
	if token == "" {
		return fmt.Errorf("huawei: no CSRF token in %s", c.baseURL+indexPath)
	}

	c.token = token
	c.session = sessionFromResponse(resp)
	return nil
}

// sessionFromResponse picks the SessionID cookie out of the response. It is
// parsed by hand because the modem formats the attributes as "path =/", which
// net/http's cookie jar does not accept.
func sessionFromResponse(resp *http.Response) string {
	for _, header := range resp.Header.Values("Set-Cookie") {
		if match := indexSessionRegexp.FindStringSubmatch(header); match != nil {
			return match[1]
		}
	}
	return ""
}

// APIError is a failure reported by the modem itself.
type APIError struct {
	// Code is the modem's numeric error code (e.g. 125003).
	Code string
	// Message is the modem's description, usually empty.
	Message string
}

func (e *APIError) Error() string {
	return fmt.Sprintf("modem error %s: %s", e.Code, e.Message)
}

// logf logs with a prefix so huawei messages are told apart in the service log.
func logf(format string, args ...any) {
	log.Printf("[huawei] "+format, args...)
}
