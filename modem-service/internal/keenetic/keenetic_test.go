package keenetic

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"
)

// fakeNDM emulates the Keenetic NDM handshake used by the sms-service mock.
type fakeNDM struct {
	mu       sync.Mutex
	login    string
	password string
	realm    string
	iface    string
	sessions map[string]string // session token -> challenge
	sms      []map[string]string
	inbox    map[string]map[string]string // id -> {from, timestamp, text}
}

func (f *fakeNDM) challenge(token string) string {
	f.mu.Lock()
	defer f.mu.Unlock()
	if _, ok := f.sessions[token]; !ok {
		f.sessions[token] = "challenge-" + token
	}
	return f.sessions[token]
}

func (f *fakeNDM) cookie(req *http.Request) string {
	for _, part := range strings.Split(req.Header.Get("Cookie"), ";") {
		part = strings.TrimSpace(part)
		if strings.HasPrefix(part, "session=") {
			return strings.TrimPrefix(part, "session=")
		}
	}
	return ""
}

func (f *fakeNDM) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	switch {
	case r.Method == http.MethodGet && r.URL.Path == "/auth":
		token := f.cookie(r)
		if token == "" {
			token = "tok-1"
		}
		challenge := f.challenge(token)
		w.Header().Set("X-NDM-Challenge", challenge)
		w.Header().Set("X-NDM-Realm", f.realm)
		w.Header().Set("Set-Cookie", "session="+token+"; Path=/")
		w.WriteHeader(http.StatusUnauthorized)
		_, _ = w.Write([]byte(`{"error":"unauthorized"}`))

	case r.Method == http.MethodPost && r.URL.Path == "/auth":
		token := f.cookie(r)
		if token == "" {
			http.Error(w, "no session", http.StatusUnauthorized)
			return
		}
		var body struct{ Login, Password string }
		_ = json.NewDecoder(r.Body).Decode(&body)
		expected := encryptPassword(f.login, f.password, f.challenge(token), f.realm)
		if body.Login != f.login || body.Password != expected {
			http.Error(w, "bad credentials", http.StatusUnauthorized)
			return
		}
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"result":"ok"}`))

	case r.Method == http.MethodPost && r.URL.Path == "/rci/":
		token := f.cookie(r)
		f.mu.Lock()
		_, ok := f.sessions[token]
		f.mu.Unlock()
		if !ok {
			http.Error(w, "not authorized", http.StatusUnauthorized)
			return
		}
		var payload []map[string]any
		_ = json.NewDecoder(r.Body).Decode(&payload)
		root := payload[0]["sms"].(map[string]any)

		if send, ok := root["send"].(map[string]any); ok {
			f.mu.Lock()
			f.sms = append(f.sms, map[string]string{
				"interface": send["interface"].(string),
				"to":        send["to"].(string),
				"message":   send["message"].(string),
			})
			f.mu.Unlock()
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte(`{"result":"Ok"}`))
			return
		}

		if root["list"] != nil {
			f.mu.Lock()
			messages := make(map[string]any, len(f.inbox))
			for id, message := range f.inbox {
				messages[id] = message
			}
			f.mu.Unlock()
			resp := []map[string]any{{
				"sms": map[string]any{
					"list": map[string]any{
						"interface": f.iface,
						"messages":  messages,
					},
				},
			}}
			w.WriteHeader(http.StatusOK)
			_ = json.NewEncoder(w).Encode(resp)
			return
		}

		if deletions, ok := root["delete"].([]any); ok {
			for _, entry := range deletions {
				item := entry.(map[string]any)
				f.mu.Lock()
				delete(f.inbox, item["id"].(string))
				f.mu.Unlock()
			}
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte(`{"result":"Ok"}`))
			return
		}

		http.Error(w, "unknown sms command", http.StatusBadRequest)

	default:
		http.NotFound(w, r)
	}
}

func TestClientSend(t *testing.T) {
	ndm := &fakeNDM{
		login:    "samsa",
		password: "modem-password",
		realm:    "Realm",
		sessions: map[string]string{},
	}
	server := httptest.NewServer(ndm)
	defer server.Close()

	client := New(server.URL, "samsa", "modem-password", "UsbLte0", 5*time.Second)

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	if err := client.Send(ctx, "+79031926703", "Тест"); err != nil {
		t.Fatalf("Send() error = %v", err)
	}

	ndm.mu.Lock()
	defer ndm.mu.Unlock()
	if len(ndm.sms) != 1 {
		t.Fatalf("expected 1 SMS stored, got %d", len(ndm.sms))
	}
	got := ndm.sms[0]
	if got["to"] != "+79031926703" || got["message"] != "Тест" || got["interface"] != "UsbLte0" {
		t.Fatalf("unexpected SMS payload: %v", got)
	}
}

func TestClientReauthenticatesOnExpiredSession(t *testing.T) {
	ndm := &fakeNDM{
		login:    "samsa",
		password: "modem-password",
		realm:    "Realm",
		sessions: map[string]string{},
	}
	rciAttempts := 0
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// The first RCI call is answered with 401, forcing the client to
		// re-authenticate and retry once, like an expired router session.
		if r.Method == http.MethodPost && r.URL.Path == "/rci/" {
			rciAttempts++
			if rciAttempts == 1 {
				http.Error(w, "not authorized", http.StatusUnauthorized)
				return
			}
		}
		ndm.ServeHTTP(w, r)
	})
	server := httptest.NewServer(handler)
	defer server.Close()

	client := New(server.URL, "samsa", "modem-password", "UsbLte0", 5*time.Second)

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	if err := client.Send(ctx, "+79031926703", "Тест"); err != nil {
		t.Fatalf("Send() error = %v", err)
	}
	if rciAttempts != 2 {
		t.Fatalf("expected 2 RCI attempts (fail + retry), got %d", rciAttempts)
	}
}

func TestClientListInbox(t *testing.T) {
	ndm := &fakeNDM{
		login:    "samsa",
		password: "modem-password",
		realm:    "Realm",
		iface:    "UsbLte0",
		sessions: map[string]string{},
		inbox: map[string]map[string]string{
			"nv-1": {"from": "+79991112233", "timestamp": "2026-09-16 10:00:00", "text": "Баланс: 100 руб."},
			"nv-2": {"from": "Beeline", "timestamp": "2026-09-16 11:00:00", "text": "Ваш код: 1234"},
		},
	}
	server := httptest.NewServer(ndm)
	defer server.Close()

	client := New(server.URL, "samsa", "modem-password", "UsbLte0", 5*time.Second)

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	messages, err := client.ListInbox(ctx)
	if err != nil {
		t.Fatalf("ListInbox() error = %v", err)
	}
	if len(messages) != 2 {
		t.Fatalf("expected 2 SMS, got %d", len(messages))
	}

	byID := map[string]IncomingSMS{}
	for _, m := range messages {
		byID[m.ID] = m
	}
	first, ok := byID["nv-1"]
	if !ok || first.From != "+79991112233" || first.Timestamp != "2026-09-16 10:00:00" || first.Text != "Баланс: 100 руб." {
		t.Fatalf("unexpected inbox entry: %+v", byID)
	}
}

func TestClientDeleteSMS(t *testing.T) {
	ndm := &fakeNDM{
		login:    "samsa",
		password: "modem-password",
		realm:    "Realm",
		iface:    "UsbLte0",
		sessions: map[string]string{},
		inbox: map[string]map[string]string{
			"nv-1": {"from": "+79991112233", "text": "Баланс"},
		},
	}
	server := httptest.NewServer(ndm)
	defer server.Close()

	client := New(server.URL, "samsa", "modem-password", "UsbLte0", 5*time.Second)

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	if err := client.DeleteSMS(ctx, "nv-1"); err != nil {
		t.Fatalf("DeleteSMS() error = %v", err)
	}

	ndm.mu.Lock()
	defer ndm.mu.Unlock()
	if len(ndm.inbox) != 0 {
		t.Fatalf("expected empty inbox, got %d messages", len(ndm.inbox))
	}
}
