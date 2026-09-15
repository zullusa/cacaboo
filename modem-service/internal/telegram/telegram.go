// Package telegram posts messages to a Telegram channel through the
// sendMessage API, mirroring the sms-service SmsPoller behaviour (including
// the optional HTTP proxy).
package telegram

import (
	"context"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"time"
)

// Sender delivers texts to a single Telegram channel.
type Sender struct {
	botToken   string
	chatID     string
	httpClient *http.Client
}

// New builds a Sender for the given bot token and channel. When proxy is
// non-empty every request is routed through it.
func New(botToken, chatID, proxy string, timeout time.Duration) *Sender {
	transport := &http.Transport{}
	if proxy != "" {
		transport.Proxy = func(*http.Request) (*url.URL, error) {
			return url.Parse(proxy)
		}
	}
	return &Sender{
		botToken:   botToken,
		chatID:     chatID,
		httpClient: &http.Client{Timeout: timeout, Transport: transport},
	}
}

// Send delivers text to the configured channel. It returns an error whenever
// the Telegram API does not confirm the delivery (network failure or a
// non-200 HTTP status), mirroring the sms-service poller.
func (s *Sender) Send(ctx context.Context, text string) error {
	endpoint := fmt.Sprintf(
		"https://api.telegram.org/bot%s/sendMessage?chat_id=%s&text=%s",
		s.botToken,
		url.QueryEscape(s.chatID),
		url.QueryEscape(text),
	)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint, nil)
	if err != nil {
		return err
	}

	resp, err := s.httpClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	body, _ := io.ReadAll(resp.Body)
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("telegram API responded with HTTP %d: %s", resp.StatusCode, truncate(string(body)))
	}
	return nil
}

func truncate(s string) string {
	if len(s) > 300 {
		return s[:300] + "..."
	}
	return s
}
