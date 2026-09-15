package keenetic

import (
	"bytes"
	"context"
	"crypto/md5"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"sync"
	"time"
)

// Client talks to a Keenetic router NDM API: it performs the challenge-response
// authentication and then runs RCI commands against a modem (e.g. UsbLte0 on
// the Beeline modem) — sending SMS, reading the SMS inbox and deleting
// forwarded messages.
type Client struct {
	baseURL  string
	login    string
	password string
	iface    string

	httpClient *http.Client
	mu         sync.Mutex
	cookie     string
}

func New(baseURL, login, password, iface string, httpTimeout time.Duration) *Client {
	return &Client{
		baseURL:    strings.TrimRight(baseURL, "/"),
		login:      login,
		password:   password,
		iface:      iface,
		httpClient: &http.Client{Timeout: httpTimeout},
	}
}

// Send delivers a single SMS through the configured modem interface.
func (c *Client) Send(ctx context.Context, phone, text string) error {
	payload := []map[string]any{{
		"sms": map[string]any{
			"send": map[string]any{
				"interface": c.iface,
				"to":        phone,
				"message":   text,
			},
		},
	}}
	status, body, err := c.call(ctx, payload)
	if err != nil {
		return err
	}
	if status != http.StatusOK {
		return fmt.Errorf("rci send failed: http %d: %s", status, truncate(string(body)))
	}
	return nil
}

// IncomingSMS is one SMS stored in the modem's inbox.
type IncomingSMS struct {
	ID        string
	From      string
	Timestamp string
	Text      string
}

// ListInbox returns every SMS currently stored on the modem interface. The
// returned IDs are the modem-local message ids (e.g. "nv-6").
func (c *Client) ListInbox(ctx context.Context) ([]IncomingSMS, error) {
	payload := []map[string]any{{
		"sms": map[string]any{
			"list": map[string]any{"interface": c.iface},
		},
	}}
	status, body, err := c.call(ctx, payload)
	if err != nil {
		return nil, err
	}
	if status != http.StatusOK {
		return nil, fmt.Errorf("rci sms list failed: http %d: %s", status, truncate(string(body)))
	}

	// The RCI reply is a list whose first element carries the inbox:
	// [{"sms":{"list":{"interface":"UsbLte0","messages":{
	//   "nv-1":{"from":..., "timestamp":..., "type":..., "text":...}, ...}}}}]
	var response []struct {
		SMS struct {
			List struct {
				Messages map[string]struct {
					From      string `json:"from"`
					Timestamp string `json:"timestamp"`
					Type      string `json:"type"`
					Text      string `json:"text"`
				} `json:"messages"`
			} `json:"list"`
		} `json:"sms"`
	}
	if err := json.Unmarshal(body, &response); err != nil {
		return nil, fmt.Errorf("unmarshal sms list: %w", err)
	}
	if len(response) == 0 {
		return nil, nil
	}

	messages := response[0].SMS.List.Messages
	result := make([]IncomingSMS, 0, len(messages))
	for id, message := range messages {
		result = append(result, IncomingSMS{
			ID:        id,
			From:      message.From,
			Timestamp: message.Timestamp,
			Text:      message.Text,
		})
	}
	return result, nil
}

// DeleteSMS removes a single SMS from the modem inbox by its local id
// (returned by ListInbox).
func (c *Client) DeleteSMS(ctx context.Context, id string) error {
	payload := []map[string]any{{
		"sms": map[string]any{
			"delete": []map[string]any{{"interface": c.iface, "id": id}},
		},
	}}
	status, body, err := c.call(ctx, payload)
	if err != nil {
		return err
	}
	if status != http.StatusOK {
		return fmt.Errorf("rci sms delete failed: http %d: %s", status, truncate(string(body)))
	}
	return nil
}

// call runs an authenticated RCI command. The first call after construction
// authenticates to the router; if the router answers 401 (e.g. an expired
// session) the client re-authenticates once and retries the request.
func (c *Client) call(ctx context.Context, payload []map[string]any) (int, []byte, error) {
	c.mu.Lock()
	defer c.mu.Unlock()

	for attempt := 0; attempt < 2; attempt++ {
		if c.cookie == "" {
			if err := c.authenticate(ctx); err != nil {
				return 0, nil, err
			}
		}

		status, body, err := c.rciPost(ctx, payload)
		if err != nil {
			return 0, nil, err
		}

		if status == http.StatusUnauthorized {
			c.cookie = ""
			continue
		}

		return status, body, nil
	}

	return http.StatusUnauthorized, nil, fmt.Errorf("rci command failed after re-authentication")
}

// authenticate performs the NDM challenge-response handshake and saves the
// session cookie for subsequent RCI calls.
func (c *Client) authenticate(ctx context.Context) error {
	challenge, realm, cookie, err := c.fetchChallenge(ctx, "")
	if err != nil {
		return err
	}

	// The first request without a cookie returns an empty challenge; fetch
	// again using the cookie handed out by the router so it issues a fresh
	// challenge for the session.
	if challenge == "" && cookie != "" {
		challenge, realm, cookie, err = c.fetchChallenge(ctx, cookie)
		if err != nil {
			return err
		}
	}

	if challenge == "" || realm == "" {
		return fmt.Errorf("missing NDM challenge/realm from %s/auth", c.baseURL)
	}

	encrypted := encryptPassword(c.login, c.password, challenge, realm)
	payload, _ := json.Marshal(map[string]string{"login": c.login, "password": encrypted})

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.baseURL+"/auth", bytes.NewReader(payload))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "application/json, text/plain, */*")
	if cookie != "" {
		req.Header.Set("Cookie", cookie)
	}

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(resp.Body)

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("keenetic auth failed: http %d: %s", resp.StatusCode, truncate(string(body)))
	}

	c.cookie = cookie
	return nil
}

// fetchChallenge reads the NDM challenge, realm and session cookie from the
// router's /auth endpoint.
func (c *Client) fetchChallenge(ctx context.Context, cookie string) (challenge, realm, sessionCookie string, err error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.baseURL+"/auth", nil)
	if err != nil {
		return "", "", "", err
	}
	req.Header.Set("Accept", "application/json, text/plain, */*")
	if cookie != "" {
		req.Header.Set("Cookie", cookie)
	}

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return "", "", "", err
	}
	defer resp.Body.Close()
	_, _ = io.Copy(io.Discard, resp.Body)

	return resp.Header.Get("X-NDM-Challenge"),
		resp.Header.Get("X-NDM-Realm"),
		strings.Split(resp.Header.Get("Set-Cookie"), ";")[0],
		nil
}

// rciPost posts an RCI command array to the router's endpoint. The caller
// must hold mu and have authenticated first (see call).
func (c *Client) rciPost(ctx context.Context, payload []map[string]any) (int, []byte, error) {
	body, err := json.Marshal(payload)
	if err != nil {
		return 0, nil, err
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.baseURL+"/rci/", bytes.NewReader(body))
	if err != nil {
		return 0, nil, err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "application/json, text/plain, */*")
	req.Header.Set("Cookie", c.cookie)

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return 0, nil, err
	}
	defer resp.Body.Close()
	rb, _ := io.ReadAll(resp.Body)
	return resp.StatusCode, rb, nil
}

// encryptPassword mirrors the Keenetic challenge-response algorithm:
// first = md5(login:realm:password), then sha256(challenge + first).
func encryptPassword(login, password, challenge, realm string) string {
	first := md5Hex(login + ":" + realm + ":" + password)
	return sha256Hex(challenge + first)
}

func md5Hex(s string) string {
	sum := md5.Sum([]byte(s))
	return hex.EncodeToString(sum[:])
}

func sha256Hex(s string) string {
	sum := sha256.Sum256([]byte(s))
	return hex.EncodeToString(sum[:])
}

func truncate(s string) string {
	if len(s) > 300 {
		return s[:300] + "..."
	}
	return s
}
