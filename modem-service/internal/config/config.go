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

	// Keenetic modem (RCI endpoint).
	ModemName     string
	ModemUser     string
	ModemPassword string
	ModemURLBase  string

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
}

func Load() (*Config, error) {
	cfg := &Config{
		Provider:          os.Getenv("PROVIDER"),
		ModemName:         os.Getenv("MODEM_NAME"),
		ModemUser:         os.Getenv("MODEM_USER"),
		ModemPassword:     os.Getenv("MODEM_PASSWORD"),
		ModemURLBase:      strings.TrimRight(os.Getenv("MODEM_URL_BASE"), "/"),
		RabbitMQHost:      getenv("RABBITMQ_HOST", "rabbitmq"),
		RabbitMQPort:      getenvInt("RABBITMQ_PORT", 5672),
		RabbitMQUser:      getenv("RABBITMQ_USER", "guest"),
		RabbitMQPassword:  getenv("RABBITMQ_PASSWORD", "guest"),
		RabbitMQVHost:     getenv("RABBITMQ_VHOST", "/"),
		RabbitMQQueue:     getenv("RABBITMQ_QUEUE", "notifications"),
		RabbitMQExchange:  os.Getenv("RABBITMQ_EXCHANGE"),
		NotifiedQueue:     getenv("RABBITMQ_NOTIFIED_QUEUE", "notified"),
		NotifiedExchange:  os.Getenv("RABBITMQ_NOTIFIED_EXCHANGE"),
		MetricsPort:       getenvInt("METRICS_PORT", 8004),
		SendTimeout:       time.Duration(getenvInt("SEND_TIMEOUT_SECONDS", 20)) * time.Second,
		HTTPTimeout:       time.Duration(getenvInt("HTTP_TIMEOUT_SECONDS", 30)) * time.Second,
		MaxRetries:        getenvInt("MAX_RETRIES", 3),
		MaxRequeue:        getenvInt("MAX_REQUEUE", 10),
		ReconnectWait:     time.Duration(getenvInt("RECONNECT_WAIT_SECONDS", 5)) * time.Second,
		RabbitMQHeartbeat: time.Duration(getenvInt("RABBITMQ_HEARTBEAT", 60)) * time.Second,
		PrefetchCount:     getenvInt("PREFETCH_COUNT", 10),
		ProviderFilter:    os.Getenv("PROVIDER_FILTER"),
		TelegramBotToken:  os.Getenv("TELEGRAM_BOT_TOKEN"),
		TelegramChannelID: os.Getenv("TELEGRAM_CHANNEL_ID"),
		TelegramProxy:     getenv("TELEGRAM_PROXY", getenv("HTTPS_PROXY", os.Getenv("https_proxy"))),
		SmsPollInterval:   time.Duration(getenvInt("SMS_POLL_INTERVAL_SECONDS", 60)) * time.Second,
		SmsIgnoreSender:   getenv("SMS_IGNORE_SENDER", "Beeline"),
		SmsIgnoreKeywords: getenv("SMS_IGNORE_KEYWORDS", "код подтверждения,код для входа,ваш код"),
	}

	if cfg.ModemName == "" || cfg.ModemUser == "" || cfg.ModemPassword == "" || cfg.ModemURLBase == "" {
		return nil, fmt.Errorf("MODEM_NAME, MODEM_USER, MODEM_PASSWORD and MODEM_URL_BASE env vars are required")
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
