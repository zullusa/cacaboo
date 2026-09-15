// Package poller periodically scans the Keenetic modem SMS inbox and forwards
// every message to a Telegram channel, mirroring the sms-service SmsPoller:
// each SMS is delivered to Telegram and only then deleted from the modem. The
// phone numbers resolve exactly like the modem worker sends them.
package poller

import (
	"context"
	"log"
	"strings"
	"time"

	"modem-service/internal/keenetic"
	"modem-service/internal/metrics"
)

// Inbox is the subset of the Keenetic client used by the poller (kept small so
// tests can substitute a fake).
type Inbox interface {
	ListInbox(ctx context.Context) ([]keenetic.IncomingSMS, error)
	DeleteSMS(ctx context.Context, id string) error
}

// Messenger delivers formatted SMS texts to a channel. *telegram.Sender is the
// production implementation; tests can substitute a fake.
type Messenger interface {
	Send(ctx context.Context, text string) error
}

// Poller polls the modem inbox and forwards each SMS to Telegram, deleting it
// once Telegram has accepted it. OTP/service messages sent by the configured
// operator are skipped so confirmation codes never leak.
type Poller struct {
	inbox          Inbox
	telegram       Messenger
	interval       time.Duration
	ignoreSender   string
	ignoreKeywords []string
	label          string
}

// New builds a poller. ignoreSender and ignoreKeywords mirror the sms-service
// SMS_IGNORE_SENDER / SMS_IGNORE_KEYWORDS settings.
func New(inbox Inbox, telegram Messenger, interval time.Duration, ignoreSender, ignoreKeywords, label string) *Poller {
	return &Poller{
		inbox:          inbox,
		telegram:       telegram,
		interval:       interval,
		ignoreSender:   strings.TrimSpace(ignoreSender),
		ignoreKeywords: splitKeywords(ignoreKeywords),
		label:          label,
	}
}

func splitKeywords(raw string) []string {
	var keywords []string
	for _, part := range strings.Split(raw, ",") {
		if keyword := strings.TrimSpace(part); keyword != "" {
			keywords = append(keywords, strings.ToLower(keyword))
		}
	}
	return keywords
}

// Run polls until ctx is cancelled. The first poll happens immediately after
// startup so messages are forwarded without waiting a full interval.
func (p *Poller) Run(ctx context.Context) {
	log.Printf(
		"SMS inbox poller started (interval=%s, ignoreSender=%q)",
		p.interval, p.ignoreSender,
	)

	p.poll(ctx)

	ticker := time.NewTicker(p.interval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			log.Printf("SMS inbox poller stopped")
			return
		case <-ticker.C:
			p.poll(ctx)
		}
	}
}

func (p *Poller) poll(ctx context.Context) {
	metrics.PollCycles.Inc(p.label)
	messages, err := p.inbox.ListInbox(ctx)
	if err != nil {
		metrics.InboxErrors.Inc(p.label)
		log.Printf("SMS inbox poll failed: %v", err)
		return
	}

	if len(messages) == 0 {
		return
	}
	log.Printf("Found %d SMS in the modem inbox", len(messages))

	for _, message := range messages {
		if p.shouldIgnore(message) {
			metrics.InboxSkipped.Inc(p.label)
			log.Printf("Ignoring SMS %s from '%s' (OTP/service message)", message.ID, message.From)
			continue
		}

		log.Printf("Forwarding SMS %s from '%s' to Telegram", message.ID, message.From)
		if err := p.telegram.Send(ctx, formatMessage(message)); err != nil {
			metrics.TelegramErrors.Inc(p.label)
			log.Printf(
				"Telegram delivery failed for SMS %s; keeping it on the modem: %v",
				message.ID, err,
			)
			continue
		}

		metrics.TelegramForwarded.Inc(p.label)
		if err := p.inbox.DeleteSMS(ctx, message.ID); err != nil {
			log.Printf("SMS %s forwarded but could not be deleted: %v", message.ID, err)
		}
	}
}

// shouldIgnore mirrors the sms-service poller: only messages from the
// configured sender whose text contains one of the OTP keywords are skipped.
func (p *Poller) shouldIgnore(message keenetic.IncomingSMS) bool {
	if p.ignoreSender == "" {
		return false
	}
	if !strings.EqualFold(strings.TrimSpace(message.From), p.ignoreSender) {
		return false
	}
	text := strings.ToLower(message.Text)
	for _, keyword := range p.ignoreKeywords {
		if strings.Contains(text, keyword) {
			return true
		}
	}
	return false
}

// formatMessage mirrors the sms-service SmsPoller message layout.
func formatMessage(message keenetic.IncomingSMS) string {
	sender := message.From
	if sender == "" {
		sender = "—"
	}
	timestamp := message.Timestamp
	if timestamp == "" {
		timestamp = "—"
	}
	return "📩 SMS\n" +
		"📱 От: " + sender + "\n" +
		"🕐 Дата: " + timestamp + "\n" +
		"💬 " + message.Text
}
