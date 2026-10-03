package config

import (
	"fmt"
	"os"
	"strconv"
	"strings"
	"time"
)

// Config holds every setting of the modem SMS worker. All values come from
// environment variables so the same binary can serve any provider by running
// it with the provider's own env file (e.g. .env.beeline, .env.mts).
type Config struct {
	// Provider is only used as a metrics label (e.g. "beeline").
	Provider string

	// ModemKind selects the modem backend: "keenetic" (a modem behind a Keenetic
	// router, reached over NDM/RCI) or "huawei" (a Huawei E3372 in NDIS mode
	// that is its own web server).
	ModemKind string

	// Keenetic modem (RCI endpoint). ModemUser / ModemPassword are only required
	// for the keenetic backend.
	ModemName     string
	ModemUser     string
	ModemPassword string
	ModemURLBase  string

	// Huawei backend: how much of the modem inbox one ListInbox call reads.
	ModemSMSPageSize int
	ModemSMSMaxPages int
	// ModemReportTimeout is how long a send waits for the operator's delivery
	// receipt. 0 disables the wait; a receipt that never arrives is never
	// treated as a failure, so no duplicate SMS is sent.
	ModemReportTimeout      time.Duration
	ModemReportPollInterval time.Duration

	// RabbitMQ consumption source (e.g. the "notifications_beeline" queue).
	RabbitMQHost       string
	RabbitMQPort       int
	RabbitMQUser       string
	RabbitMQPassword   string
	RabbitMQVHost      string
	RabbitMQQueue      string
	RabbitMQExchange   string
	RabbitMQRoutingKey string
	RabbitMQHeartbeat  time.Duration
	PrefetchCount      int

	// Notified feedback queue (published after a successful send).
	NotifiedQueue      string
	NotifiedExchange   string
	NotifiedRoutingKey string

	// Runtime tunables.
	MetricsPort   int
	SendTimeout   time.Duration
	HTTPTimeout   time.Duration
	MaxRetries    int
	MaxRequeue    int
	ReconnectWait time.Duration

	// ProviderFilter is the "provider" routing key this instance reacts to
	// (e.g. "beeline"). Empty means no filtering (handle every message).
	ProviderFilter string

	// Telegram forwarding of the modem SMS inbox (mirrors the sms-service
	// SmsPoller). The poller is disabled when the token or channel is empty.
	TelegramBotToken  string
	TelegramChannelID string
	TelegramProxy     string
	SmsPollInterval   time.Duration
	SmsIgnoreSender   string
	SmsIgnoreKeywords string
	// SmsIgnoreBefore is an optional cut-off: messages the modem stored before it
	// stay on the modem instead of being forwarded to Telegram. It keeps a fresh
	// worker from dumping the whole historical inbox. Accepts both the modem
	// wall-clock format ("2026-10-03 10:48:00", host timezone) and RFC3339.
	SmsIgnoreBefore time.Time
}

// Modem backend identifiers.
const (
	ModemKindKeenetic = "keenetic"
	ModemKindHuawei   = "huawei"
)

func Load() (*Config, error) {
	cfg := &Config{
		Provider:                os.Getenv("PROVIDER"),
		ModemKind:               strings.ToLower(getenv("MODEM_KIND", ModemKindKeenetic)),
		ModemName:               os.Getenv("MODEM_NAME"),
		ModemUser:               os.Getenv("MODEM_USER"),
		ModemPassword:           os.Getenv("MODEM_PASSWORD"),
		ModemURLBase:            strings.TrimRight(os.Getenv("MODEM_URL_BASE"), "/"),
		RabbitMQHost:            getenv("RABBITMQ_HOST", "rabbitmq"),
		RabbitMQPort:            getenvInt("RABBITMQ_PORT", 5672),
		RabbitMQUser:            getenv("RABBITMQ_USER", "guest"),
		RabbitMQPassword:        getenv("RABBITMQ_PASSWORD", "guest"),
		RabbitMQVHost:           getenv("RABBITMQ_VHOST", "/"),
		RabbitMQQueue:           getenv("RABBITMQ_QUEUE", "notifications"),
		RabbitMQExchange:        os.Getenv("RABBITMQ_EXCHANGE"),
		NotifiedQueue:           getenv("RABBITMQ_NOTIFIED_QUEUE", "notified"),
		NotifiedExchange:        os.Getenv("RABBITMQ_NOTIFIED_EXCHANGE"),
		MetricsPort:             getenvInt("METRICS_PORT", 8004),
		SendTimeout:             time.Duration(getenvInt("SEND_TIMEOUT_SECONDS", 20)) * time.Second,
		HTTPTimeout:             time.Duration(getenvInt("HTTP_TIMEOUT_SECONDS", 30)) * time.Second,
		MaxRetries:              getenvInt("MAX_RETRIES", 3),
		MaxRequeue:              getenvInt("MAX_REQUEUE", 10),
		ReconnectWait:           time.Duration(getenvInt("RECONNECT_WAIT_SECONDS", 5)) * time.Second,
		RabbitMQHeartbeat:       time.Duration(getenvInt("RABBITMQ_HEARTBEAT", 60)) * time.Second,
		PrefetchCount:           getenvInt("PREFETCH_COUNT", 10),
		ProviderFilter:          os.Getenv("PROVIDER_FILTER"),
		TelegramBotToken:        os.Getenv("TELEGRAM_BOT_TOKEN"),
		TelegramChannelID:       os.Getenv("TELEGRAM_CHANNEL_ID"),
		TelegramProxy:           getenv("TELEGRAM_PROXY", getenv("HTTPS_PROXY", os.Getenv("https_proxy"))),
		SmsPollInterval:         time.Duration(getenvInt("SMS_POLL_INTERVAL_SECONDS", 60)) * time.Second,
		SmsIgnoreSender:         getenv("SMS_IGNORE_SENDER", "Beeline"),
		SmsIgnoreKeywords:       getenv("SMS_IGNORE_KEYWORDS", "код подтверждения,код для входа,ваш код"),
		ModemSMSPageSize:        getenvInt("MODEM_SMS_PAGE_SIZE", 20),
		ModemSMSMaxPages:        getenvInt("MODEM_SMS_MAX_PAGES", 5),
		ModemReportTimeout:      time.Duration(getenvInt("MODEM_REPORT_TIMEOUT_SECONDS", 0)) * time.Second,
		ModemReportPollInterval: time.Duration(getenvInt("MODEM_REPORT_POLL_SECONDS", 5)) * time.Second,
	}

	if cfg.ModemURLBase == "" {
		return nil, fmt.Errorf("MODEM_URL_BASE env var is required")
	}
	if cfg.ModemKind != ModemKindKeenetic && cfg.ModemKind != ModemKindHuawei {
		return nil, fmt.Errorf(
			"unsupported MODEM_KIND %q, expected %s or %s",
			cfg.ModemKind, ModemKindKeenetic, ModemKindHuawei,
		)
	}
	// The huawei backend talks to the modem's own web server, which needs no
	// router credentials; the keenetic backend always does.
	if cfg.ModemKind == ModemKindKeenetic && (cfg.ModemName == "" || cfg.ModemUser == "" || cfg.ModemPassword == "") {
		return nil, fmt.Errorf(
			"MODEM_NAME, MODEM_USER and MODEM_PASSWORD env vars are required for MODEM_KIND=%s",
			ModemKindKeenetic,
		)
	}

	if raw := strings.TrimSpace(os.Getenv("SMS_IGNORE_BEFORE")); raw != "" {
		cutoff, err := ParseInboxCutoff(raw)
		if err != nil {
			return nil, err
		}
		cfg.SmsIgnoreBefore = cutoff
	}

	if cfg.RabbitMQRoutingKey == "" {
		cfg.RabbitMQRoutingKey = cfg.RabbitMQQueue
	}
	if cfg.NotifiedRoutingKey == "" {
		cfg.NotifiedRoutingKey = cfg.NotifiedQueue
	}
	if cfg.Provider == "" {
		cfg.Provider = "modem"
	}

	return cfg, nil
}

// modemTimeLayout is the timestamp layout the modems store ("2026-10-03
// 10:48:00") with no timezone marker, so it is read as host-local time — the
// same assumption the poller makes when it compares a message against the
// cut-off.
const modemTimeLayout = "2006-01-02 15:04:05"

// ParseInboxCutoff reads SMS_IGNORE_BEFORE. The modem writes its timestamps in
// its own wall clock, so the bare layout is understood first and interpreted in
// the host timezone; RFC3339 is accepted too, which is handy when the cut-off
// comes from a real clock with a known offset. The live checks reuse it so the
// operator tests a cut-off parsed exactly like production does.
func ParseInboxCutoff(raw string) (time.Time, error) {
	if cutoff, err := time.ParseInLocation(modemTimeLayout, raw, time.Local); err == nil {
		return cutoff, nil
	}
	if cutoff, err := time.Parse(time.RFC3339, raw); err == nil {
		return cutoff, nil
	}
	return time.Time{}, fmt.Errorf(
		"SMS_IGNORE_BEFORE %q is malformed, expected %q (modem local time) or RFC3339 (e.g. 2026-10-03T09:57:00Z)",
		raw, modemTimeLayout,
	)
}

func getenv(key, fallback string) string {
	if v := strings.TrimSpace(os.Getenv(key)); v != "" {
		return v
	}
	return fallback
}

func getenvInt(key string, fallback int) int {
	v := strings.TrimSpace(os.Getenv(key))
	if v == "" {
		return fallback
	}
	n, err := strconv.Atoi(v)
	if err != nil {
		return fallback
	}
	return n
}
