package metrics

import (
	"bytes"
	"fmt"
	"io"
	"net/http"
	"sort"
	"sync"
)

// Counter is a minimal Prometheus counter supporting an optional provider
// label. The exposition format is written by hand so the worker has no metric
// client dependency.
type Counter struct {
	name   string
	help   string
	mu     sync.Mutex
	values map[string]int64
}

func NewCounter(name, help string) *Counter {
	return &Counter{name: name, help: help, values: make(map[string]int64)}
}

// Inc adds one to the counter for the given label value ("" for no label).
func (c *Counter) Inc(label string) { c.Add(label, 1) }

// Add adds n to the counter for the given label value.
func (c *Counter) Add(label string, n int64) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.values[label] += n
}

func (c *Counter) render(buf *bytes.Buffer) {
	c.mu.Lock()
	keys := make([]string, 0, len(c.values))
	for k := range c.values {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	values := make(map[string]int64, len(c.values))
	for k, v := range c.values {
		values[k] = v
	}
	c.mu.Unlock()

	fmt.Fprintf(buf, "# HELP %s %s\n", c.name, c.help)
	fmt.Fprintf(buf, "# TYPE %s counter\n", c.name)
	for _, label := range keys {
		if label == "" {
			fmt.Fprintf(buf, "%s %d\n", c.name, values[label])
		} else {
			fmt.Fprintf(buf, "%s{provider=%q} %d\n", c.name, label, values[label])
		}
	}
}

var (
	// MessagesDrained counts messages consumed from the provider queue.
	MessagesDrained = NewCounter("modem_messages_drained_total", "Messages consumed from the provider queue")
	// MessagesInvalid counts malformed messages that were dropped.
	MessagesInvalid = NewCounter("modem_messages_invalid_total", "Malformed messages dropped")
	// MessagesSent counts successful Keenetic sends.
	MessagesSent = NewCounter("modem_messages_sent_total", "Messages handed to the modem")
	// MessagesFailed counts failed send attempts.
	MessagesFailed = NewCounter("modem_messages_failed_total", "Send attempts that failed")
	// MessagesDropped counts messages dropped after exhausting retries.
	MessagesDropped = NewCounter("modem_messages_dropped_total", "Messages dropped after exhausting retries")
	// MessagesSkipped counts messages of another provider that were requeued or
	// dropped because this instance is not configured for that provider.
	MessagesSkipped = NewCounter("modem_messages_skipped_total", "Messages not for this provider instance")
	// PollCycles counts modem SMS inbox poll cycles.
	PollCycles = NewCounter("modem_sms_poll_cycles_total", "Modem SMS inbox poll cycles")
	// InboxErrors counts poll cycles that failed to read the modem inbox.
	InboxErrors = NewCounter("modem_sms_inbox_errors_total", "Failed modem SMS inbox polls")
	// TelegramForwarded counts SMS forwarded to Telegram and deleted from the inbox.
	TelegramForwarded = NewCounter("modem_telegram_forwarded_total", "SMS forwarded to Telegram")
	// TelegramErrors counts SMS that could not be delivered to Telegram.
	TelegramErrors = NewCounter("modem_telegram_errors_total", "Telegram delivery failures")
	// InboxSkipped counts SMS skipped as OTP/service messages.
	InboxSkipped = NewCounter("modem_sms_inbox_skipped_total", "SMS skipped as OTP/service messages")
	// NotifiedPublished counts appointment ids published to the notified queue.
	NotifiedPublished = NewCounter("modem_notified_published_total", "Appointment ids published to the notified queue")
	// PublishErrors counts failures publishing to the notified queue.
	PublishErrors = NewCounter("modem_publish_errors_total", "Failures publishing to the notified queue")
	// AuthErrors counts Keenetic authentication failures.
	AuthErrors = NewCounter("modem_auth_errors_total", "Keenetic authentication failures")
	// Reconnects counts RabbitMQ connection re-establishments.
	Reconnects = NewCounter("modem_rabbitmq_reconnects_total", "RabbitMQ reconnections")
)

var allCounters = []*Counter{
	MessagesDrained,
	MessagesInvalid,
	MessagesSent,
	MessagesFailed,
	MessagesDropped,
	MessagesSkipped,
	NotifiedPublished,
	PublishErrors,
	AuthErrors,
	Reconnects,
	PollCycles,
	InboxErrors,
	TelegramForwarded,
	TelegramErrors,
	InboxSkipped,
}

// Handler builds the HTTP handler serving /metrics and /healthz.
func Handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/metrics", func(w http.ResponseWriter, _ *http.Request) {
		var buf bytes.Buffer
		for _, c := range allCounters {
			c.render(&buf)
		}
		w.Header().Set("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
		w.WriteHeader(http.StatusOK)
		_, _ = io.Copy(w, &buf)
	})
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("ok"))
	})
	return mux
}
