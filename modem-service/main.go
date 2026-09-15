package main

import (
	"context"
	"errors"
	"log"
	"net"
	"net/http"
	"os"
	"os/signal"
	"strconv"
	"syscall"
	"time"

	amqp "github.com/rabbitmq/amqp091-go"

	"modem-service/internal/config"
	"modem-service/internal/keenetic"
	"modem-service/internal/metrics"
	"modem-service/internal/poller"
	"modem-service/internal/queue"
	"modem-service/internal/telegram"
	"modem-service/internal/worker"
)

func main() {
	log.SetFlags(log.LstdFlags | log.Lmsgprefix)
	log.SetPrefix("[modem-service] ")

	cfg, err := config.Load()
	if err != nil {
		log.Fatalf("invalid configuration: %v", err)
	}

	go serveMetrics(cfg.MetricsPort, cfg.Provider)

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	client := keenetic.New(
		cfg.ModemURLBase,
		cfg.ModemUser,
		cfg.ModemPassword,
		cfg.ModemName,
		cfg.HTTPTimeout,
	)

	startPoller(ctx, cfg, client)

	consumer := queue.NewConsumer(queue.Config{
		Host:       cfg.RabbitMQHost,
		Port:       cfg.RabbitMQPort,
		User:       cfg.RabbitMQUser,
		Password:   cfg.RabbitMQPassword,
		VHost:      cfg.RabbitMQVHost,
		Queue:      cfg.RabbitMQQueue,
		Exchange:   cfg.RabbitMQExchange,
		RoutingKey: cfg.RabbitMQRoutingKey,
		Heartbeat:  cfg.RabbitMQHeartbeat,
		Prefetch:   cfg.PrefetchCount,
	})

	handlerQueue(ctx, consumer, worker.New(cfg, client))
}

// startPoller launches the modem inbox -> Telegram forwarder unless the
// Telegram integration is not configured.
func startPoller(ctx context.Context, cfg *config.Config, client *keenetic.Client) {
	if cfg.TelegramBotToken == "" || cfg.TelegramChannelID == "" {
		log.Printf("SMS inbox poller disabled (requires TELEGRAM_BOT_TOKEN and TELEGRAM_CHANNEL_ID)")
		return
	}

	sender := telegram.New(
		cfg.TelegramBotToken,
		cfg.TelegramChannelID,
		cfg.TelegramProxy,
		15*time.Second,
	)
	p := poller.New(
		client,
		sender,
		cfg.SmsPollInterval,
		cfg.SmsIgnoreSender,
		cfg.SmsIgnoreKeywords,
		cfg.Provider,
	)
	go p.Run(ctx)
}

// handlerQueue adapts the consumer.Run signature to the worker handler.
func handlerQueue(ctx context.Context, consumer *queue.Consumer, w *worker.Worker) {
	err := consumer.Run(ctx, func(inner context.Context, d amqp.Delivery) {
		w.Handle(inner, consumer, d)
	})
	if err != nil && !errors.Is(err, context.Canceled) {
		log.Fatalf("consumer stopped: %v", err)
	}
	log.Printf("shutting down")
}

func serveMetrics(port int, provider string) {
	addr := net.JoinHostPort("", strconv.Itoa(port))
	server := &http.Server{
		Addr:    addr,
		Handler: metrics.Handler(),
	}
	log.Printf("metrics server listening on %s/metrics (provider=%s)", addr, provider)
	if err := server.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
		log.Printf("metrics server error: %v", err)
	}
}
