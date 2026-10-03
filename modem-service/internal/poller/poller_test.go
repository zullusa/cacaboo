package poller

import (
	"context"
	"errors"
	"strings"
	"testing"
	"time"

	"modem-service/internal/modem"
)

func TestPollForwardsAndDeletes(t *testing.T) {
	inbox := &fakeInbox{
		messages: []modem.IncomingSMS{
			{ID: "nv-1", From: "+79991112233", Timestamp: "2026-09-16 10:00:00", Text: "Баланс: 100 руб."},
			{ID: "nv-2", From: "+79992223344", Timestamp: "2026-09-16 11:00:00", Text: "Здравствуйте!"},
		},
	}
	messenger := &fakeMessenger{}
	p := New(inbox, messenger, time.Minute, "", "", "test", time.Time{})

	p.Poll(context.Background())

	if len(messenger.texts) != 2 {
		t.Fatalf("expected 2 Telegram sends, got %d", len(messenger.texts))
	}
	if len(inbox.deleted) != 2 {
		t.Fatalf("expected 2 deletions, got %v", inbox.deleted)
	}
	if got := messenger.texts[0]; got != "📩 SMS\n📱 От: +79991112233\n🕐 Дата: 2026-09-16 10:00:00\n💬 Баланс: 100 руб." {
		t.Fatalf("unexpected formatted message:\n%s", got)
	}
}

func TestPollIgnoresOTPFromConfiguredSender(t *testing.T) {
	inbox := &fakeInbox{
		messages: []modem.IncomingSMS{
			{ID: "nv-1", From: "Beeline", Text: "Ваш код подтверждения: 1234"},
			{ID: "nv-2", From: "+79991112233", Text: "Обычное сообщение"},
		},
	}
	messenger := &fakeMessenger{}
	p := New(inbox, messenger, time.Minute, "Beeline", "код подтверждения,код для входа,ваш код", "test", time.Time{})

	p.Poll(context.Background())

	if len(messenger.texts) != 1 {
		t.Fatalf("expected 1 Telegram send (OTP skipped), got %d", len(messenger.texts))
	}
	if got := inbox.deleted; len(got) != 1 || got[0] != "nv-2" {
		t.Fatalf("expected only nv-2 to be deleted, got %v", got)
	}
}

func TestPollKeepsMessageWhenTelegramFails(t *testing.T) {
	inbox := &fakeInbox{
		messages: []modem.IncomingSMS{
			{ID: "nv-1", From: "+79991112233", Text: "Баланс"},
		},
	}
	messenger := &fakeMessenger{err: errors.New("network down")}
	p := New(inbox, messenger, time.Minute, "", "", "test", time.Time{})

	p.Poll(context.Background())

	if len(messenger.texts) != 1 {
		t.Fatalf("expected 1 send attempt, got %d", len(messenger.texts))
	}
	if len(inbox.deleted) != 0 {
		t.Fatalf("message must stay on the modem when Telegram fails, deleted=%v", inbox.deleted)
	}
}

func TestShouldIgnore(t *testing.T) {
	tests := []struct {
		name     string
		sms      modem.IncomingSMS
		expected bool
	}{
		{
			name:     "OTP from configured sender",
			sms:      modem.IncomingSMS{From: "Beeline", Text: "Ваш код подтверждения: 1234"},
			expected: true,
		},
		{
			name:     "case-insensitive match",
			sms:      modem.IncomingSMS{From: "beeline", Text: "ВАШ КОД: 1234"},
			expected: true,
		},
		{
			name:     "other sender is forwarded",
			sms:      modem.IncomingSMS{From: "+79991112233", Text: "Ваш код подтверждения"},
			expected: false,
		},
		{
			name:     "no keyword match",
			sms:      modem.IncomingSMS{From: "Beeline", Text: "Баланс: 100 руб."},
			expected: false,
		},
		{
			name:     "empty ignore sender forwards everything",
			sms:      modem.IncomingSMS{From: "Beeline", Text: "Ваш код подтверждения"},
			expected: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			p := New(nil, nil, 0, "Beeline", "код подтверждения,ваш код", "test", time.Time{})
			if tt.name == "empty ignore sender forwards everything" {
				p = New(nil, nil, 0, "", "код подтверждения,ваш код", "test", time.Time{})
			}
			if got := p.shouldIgnore(tt.sms); got != tt.expected {
				t.Fatalf("shouldIgnore(%+v) = %v, want %v", tt.sms, got, tt.expected)
			}
		})
	}
}

func TestPollKeepsMessagesOlderThanTheCutoff(t *testing.T) {
	// The modems store local wall-clock timestamps, so the cut-off is local too.
	cutoff := time.Date(2026, 10, 3, 10, 0, 0, 0, time.Local)
	inbox := &fakeInbox{
		messages: []modem.IncomingSMS{
			{ID: "40040", From: "+79991112233", Timestamp: "2026-10-02 16:38:00", Text: "Старое"},
			{ID: "40048", From: "+79991112233", Timestamp: "2026-10-03 10:48:00", Text: "Новое"},
		},
	}
	messenger := &fakeMessenger{}
	p := New(inbox, messenger, time.Minute, "", "", "test", cutoff)

	p.Poll(context.Background())

	if len(messenger.texts) != 1 || !strings.Contains(messenger.texts[0], "Новое") {
		t.Fatalf("expected only the message newer than the cutoff to be forwarded, got %v", messenger.texts)
	}
	if got := inbox.deleted; len(got) != 1 || got[0] != "40048" {
		t.Fatalf("expected only 40048 to be deleted, got %v", got)
	}
}

func TestPollForwardsMessagesWithUnparsableTimestamps(t *testing.T) {
	// The modems store local wall-clock timestamps, so the cut-off is local too.
	cutoff := time.Date(2026, 10, 3, 10, 0, 0, 0, time.Local)
	inbox := &fakeInbox{
		messages: []modem.IncomingSMS{
			{ID: "1", From: "+79991112233", Timestamp: "сегодня", Text: "Свежее"},
		},
	}
	messenger := &fakeMessenger{}
	p := New(inbox, messenger, time.Minute, "", "", "test", cutoff)

	p.Poll(context.Background())

	if len(messenger.texts) != 1 {
		t.Fatalf("a message with an unreadable timestamp must still be forwarded, got %v", messenger.texts)
	}
}

// fakeInbox stands in for a modem inbox.
type fakeInbox struct {
	messages []modem.IncomingSMS
	deleted  []string
}

func (f *fakeInbox) ListInbox(_ context.Context) ([]modem.IncomingSMS, error) {
	return f.messages, nil
}

func (f *fakeInbox) DeleteSMS(_ context.Context, id string) error {
	f.deleted = append(f.deleted, id)
	return nil
}

// fakeMessenger stands in for the Telegram sender.
type fakeMessenger struct {
	err   error
	texts []string
}

func (f *fakeMessenger) Send(_ context.Context, text string) error {
	f.texts = append(f.texts, text)
	return f.err
}
