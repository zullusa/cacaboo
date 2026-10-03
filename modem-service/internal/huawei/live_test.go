//go:build live

package huawei_test

// Live checks of the Huawei E3372 backend and of the modem inbox -> Telegram
// forwarder. Both are skipped unless the environment names a modem:
//
//	MODEM_URL=http://192.168.8.1 go test -tags live -v ./internal/huawei
//
// Sending is opt-in and bounded by the operator, so it needs two more vars:
//
//	MODEM_LIVE_SEND=1 MODEM_LIVE_PHONE=+7903… MODEM_LIVE_TEXT='привет'
//
// The forwarder additionally needs Telegram credentials and a cut-off so only
// fresh messages reach the channel (it deletes them from the modem). The
// cut-off takes the same two formats as SMS_IGNORE_BEFORE:
//
//	TELEGRAM_BOT_TOKEN=… TELEGRAM_CHANNEL_ID=… \
//	  MODEM_LIVE_FORWARD=1 MODEM_LIVE_SMS_IGNORE_BEFORE='2026-10-03 10:57:00'

import (
	"context"
	"os"
	"testing"
	"time"

	"modem-service/internal/config"
	"modem-service/internal/huawei"
	"modem-service/internal/poller"
	"modem-service/internal/telegram"
)

// liveClient builds a backend for the modem named by MODEM_URL.
func liveClient(t *testing.T, reportTimeout time.Duration) *huawei.Client {
	t.Helper()
	base := os.Getenv("MODEM_URL")
	if base == "" {
		t.Skip("MODEM_URL is not set")
	}
	return huawei.New(huawei.Options{
		BaseURL:            base,
		HTTPTimeout:        10 * time.Second,
		PageSize:           20,
		MaxPages:           5,
		ReportTimeout:      reportTimeout,
		ReportPollInterval: 3 * time.Second,
	})
}

func TestLive(t *testing.T) {
	client := liveClient(t, 0)
	ctx, cancel := context.WithTimeout(context.Background(), 90*time.Second)
	defer cancel()

	count, err := client.GetCount(ctx)
	if err != nil {
		t.Fatalf("GetCount: %v", err)
	}
	t.Logf("modem counters: %+v", count)

	messages, err := client.ListInbox(ctx)
	if err != nil {
		t.Fatalf("ListInbox: %v", err)
	}
	t.Logf("inbox holds %d messages", len(messages))
	for _, message := range messages {
		t.Logf("  [%s] %s from %s: %s", message.ID, message.Timestamp, message.From, message.Text)
	}

	if os.Getenv("MODEM_LIVE_SEND") == "" {
		return
	}

	// A second client so the send can wait for the operator's receipt.
	sender := liveClient(t, 90*time.Second)
	started := time.Now()
	if err := sender.Send(ctx, os.Getenv("MODEM_LIVE_PHONE"), os.Getenv("MODEM_LIVE_TEXT")); err != nil {
		t.Fatalf("Send: %v", err)
	}
	t.Logf("send confirmed by the delivery receipt in %s", time.Since(started).Round(time.Second))
}

// TestLiveForwardToTelegram runs the production poller once against the real
// modem and the real channel. Messages older than
// MODEM_LIVE_SMS_IGNORE_BEFORE are left untouched; everything that is forwarded
// is deleted from the modem, exactly like in production.
func TestLiveForwardToTelegram(t *testing.T) {
	if os.Getenv("MODEM_LIVE_FORWARD") == "" {
		t.Skip("MODEM_LIVE_FORWARD is not set")
	}
	token := os.Getenv("TELEGRAM_BOT_TOKEN")
	channel := os.Getenv("TELEGRAM_CHANNEL_ID")
	if token == "" || channel == "" {
		t.Skip("TELEGRAM_BOT_TOKEN and TELEGRAM_CHANNEL_ID are required to forward")
	}

	var cutoff time.Time
	if raw := os.Getenv("MODEM_LIVE_SMS_IGNORE_BEFORE"); raw != "" {
		parsed, err := config.ParseInboxCutoff(raw)
		if err != nil {
			t.Fatalf("MODEM_LIVE_SMS_IGNORE_BEFORE: %v", err)
		}
		cutoff = parsed
	}

	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()

	client := liveClient(t, 0)
	forwarder := poller.New(
		client,
		telegram.New(token, channel, os.Getenv("TELEGRAM_PROXY"), 15*time.Second),
		time.Minute,
		os.Getenv("SMS_IGNORE_SENDER"),
		os.Getenv("SMS_IGNORE_KEYWORDS"),
		"live",
		cutoff,
	)

	forwarder.Poll(ctx)
}
