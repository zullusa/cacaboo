package huawei

import (
	"encoding/xml"
	"errors"
	"fmt"
	"regexp"
	"strconv"
	"strings"

	"modem-service/internal/modem"
)

// sendRequest is the body of POST /api/sms/send-sms. Index -1 means "new
// message" (a draft would carry its own index). Phones is the recipient list.
type sendRequest struct {
	XMLName  xml.Name `xml:"request"`
	Index    string   `xml:"Index"`
	Phones   []string `xml:"Phones>Phone"`
	Sca      string   `xml:"Sca"`
	Content  string   `xml:"Content"`
	Length   int      `xml:"Length"`
	Reserved string   `xml:"Reserved"`
	Date     string   `xml:"Date"`
}

// listRequest is the body of POST /api/sms/sms-list. BoxType selects the box
// (1 = local inbox); SortType 0 / Ascending 0 returns newest first.
type listRequest struct {
	XMLName         xml.Name `xml:"request"`
	PageIndex       int      `xml:"PageIndex"`
	ReadCount       int      `xml:"ReadCount"`
	BoxType         int      `xml:"BoxType"`
	SortType        int      `xml:"SortType"`
	Ascending       int      `xml:"Ascending"`
	UnreadPreferred int      `xml:"UnreadPreferred"`
}

// indexRequest is the body of POST /api/sms/delete-sms and set-read.
type indexRequest struct {
	XMLName xml.Name `xml:"request"`
	Index   string   `xml:"Index"`
}

// listResponse is the reply to a sms-list call.
type listResponse struct {
	XMLName  xml.Name       `xml:"response"`
	Count    int            `xml:"Count"`
	Messages []messageEntry `xml:"Messages>Message"`
}

// messageEntry is one <Message> of the modem's inbox.
type messageEntry struct {
	Index    string `xml:"Index"`
	Phone    string `xml:"Phone"`
	Content  string `xml:"Content"`
	Date     string `xml:"Date"`
	Sca      string `xml:"Sca"`
	SaveType string `xml:"SaveType"`
	Priority string `xml:"Priority"`
	SmsType  string `xml:"SmsType"`
	Smstat   string `xml:"Smstat"`
}

// isReport reports whether the entry is the operator's delivery receipt of a
// message we sent (7 = delivered, 8 = failed). The modem files those in the same
// inbox and leaves their content empty.
func (e messageEntry) isReport() bool {
	switch atoi(e.SmsType) {
	case smsTypeReportDelivered, smsTypeReportFailed:
		return true
	default:
		return false
	}
}

// unread reports Smstat == 0, the modem's "not read yet" flag.
func (e messageEntry) unread() bool {
	return atoi(e.Smstat) == 0
}

// incoming converts an inbox entry into the vendor-independent form the poller
// consumes. A delivery receipt carries no body, so a readable one is built from
// its type — that is what makes the receipt useful to confirm a send.
func (e messageEntry) incoming() modem.IncomingSMS {
	content := e.Content
	if e.isReport() && strings.TrimSpace(content) == "" {
		if atoi(e.SmsType) == smsTypeReportFailed {
			content = "❌ доставка не удалась"
		} else {
			content = "✅ доставлено"
		}
	}
	return modem.IncomingSMS{
		ID:        e.Index,
		From:      e.Phone,
		Timestamp: e.Date,
		Text:      content,
	}
}

// countResponse is the reply to GET /api/sms/sms-count.
type countResponse struct {
	XMLName      xml.Name `xml:"response"`
	LocalUnread  int      `xml:"LocalUnread"`
	LocalInbox   int      `xml:"LocalInbox"`
	LocalOutbox  int      `xml:"LocalOutbox"`
	LocalDraft   int      `xml:"LocalDraft"`
	LocalDeleted int      `xml:"LocalDeleted"`
	SimInbox     int      `xml:"SimInbox"`
	NewMessages  int      `xml:"NewMsg"`
}

// errorResponse is the modem's failure document.
type errorResponse struct {
	XMLName xml.Name `xml:"error"`
	Code    string   `xml:"code"`
	Message string   `xml:"message"`
}

// buildXML renders a request behind the XML prolog the modem's parser requires.
// A truncated prolog (a copy of just `"1.0" encoding="UTF-8"?>`) makes the
// modem answer 100005. The payload is emitted exactly like the WebUI's
// object2xml(): prolog and root element with no whitespace in between.
func buildXML(value any) (string, error) {
	body, err := xml.Marshal(value)
	if err != nil {
		return "", fmt.Errorf("huawei: cannot encode the modem request: %w", err)
	}
	return strings.TrimSuffix(xml.Header, "\n") + string(body), nil
}

// apiError turns a modem `<error>` reply into a Go error and returns nil for a
// successful reply.
func apiError(body []byte) error {
	var failure errorResponse
	if err := xml.Unmarshal(body, &failure); err != nil {
		return nil // not an error document, let the caller parse it
	}
	if failure.Code == "" {
		return nil
	}
	message := strings.TrimSpace(failure.Message)
	if message == "" {
		message = "no message"
	}
	return &APIError{Code: failure.Code, Message: message}
}

// isSessionError reports whether the failure can be recovered from by starting a
// new session, i.e. the modem retired our cookie or our CSRF token.
func isSessionError(err error) bool {
	var apiErr *APIError
	if !errors.As(err, &apiErr) {
		return false
	}
	switch apiErr.Code {
	case errCodeWrongToken, errCodeWrongSession, errCodeStaleToken:
		return true
	default:
		return false
	}
}

// expectOK checks the `<response>OK</response>` acknowledgement the modem returns
// for the SMS commands it applied.
func expectOK(body []byte) error {
	var response struct {
		Text string `xml:",chardata"`
	}
	if err := xml.Unmarshal(body, &response); err != nil {
		return fmt.Errorf("cannot parse the reply: %w", err)
	}
	ack := strings.TrimSpace(response.Text)
	if !strings.EqualFold(ack, "ok") {
		return fmt.Errorf("unexpected reply %q", truncate(ack))
	}
	return nil
}

func firstSubmatch(pattern *regexp.Regexp, s string) string {
	match := pattern.FindStringSubmatch(s)
	if len(match) < 2 {
		return ""
	}
	return match[1]
}

func truncate(s string) string {
	if len(s) > 300 {
		return s[:300] + "..."
	}
	return s
}

// atoi is a forgiving int parser: the modem pads and may leave out numeric fields.
func atoi(raw string) int {
	n, err := strconv.Atoi(strings.TrimSpace(raw))
	if err != nil {
		return 0
	}
	return n
}
