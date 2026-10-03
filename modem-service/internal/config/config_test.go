package config

import (
	"testing"
	"time"
)

// setEnv points the process at a modem configuration and clears every other
// setting that could leak in from the developer machine.
func setEnv(t *testing.T, values map[string]string) {
	t.Helper()
	for _, key := range []string{
		"PROVIDER", "MODEM_KIND", "MODEM_NAME", "MODEM_USER", "MODEM_PASSWORD",
		"MODEM_URL_BASE", "MODEM_SMS_PAGE_SIZE", "MODEM_SMS_MAX_PAGES",
		"MODEM_REPORT_TIMEOUT_SECONDS", "MODEM_REPORT_POLL_SECONDS", "SMS_IGNORE_BEFORE",
	} {
		t.Setenv(key, "")
	}
	for key, value := range values {
		t.Setenv(key, value)
	}
}

func TestLoadKeeneticKeepsRequiringRouterCredentials(t *testing.T) {
	setEnv(t, map[string]string{
		"MODEM_KIND":     "keenetic",
		"MODEM_URL_BASE": "http://192.168.0.26",
	})
	if _, err := Load(); err == nil {
		t.Fatal("a keenetic modem without MODEM_NAME/USER/PASSWORD must be rejected")
	}
}

func TestLoadHuaweiNeedsNoRouterCredentials(t *testing.T) {
	setEnv(t, map[string]string{
		"MODEM_KIND":     "huawei",
		"MODEM_URL_BASE": "http://192.168.8.1/",
	})

	cfg, err := Load()
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	if cfg.ModemKind != ModemKindHuawei {
		t.Fatalf("expected the huawei backend, got %q", cfg.ModemKind)
	}
	if cfg.ModemURLBase != "http://192.168.8.1" {
		t.Fatalf("the base URL must lose its trailing slash, got %q", cfg.ModemURLBase)
	}
	if cfg.ModemSMSPageSize != 20 || cfg.ModemSMSMaxPages != 5 {
		t.Fatalf("unexpected inbox paging defaults: %d pages of %d", cfg.ModemSMSMaxPages, cfg.ModemSMSPageSize)
	}
	if cfg.ModemReportTimeout != 0 {
		t.Fatalf("waiting for a receipt must be opt-in, got %s", cfg.ModemReportTimeout)
	}
}

func TestLoadKeeneticIsTheDefault(t *testing.T) {
	setEnv(t, map[string]string{
		"MODEM_URL_BASE": "http://192.168.0.26",
		"MODEM_NAME":     "UsbLte0",
		"MODEM_USER":     "samsa",
		"MODEM_PASSWORD": "secret",
	})

	cfg, err := Load()
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	if cfg.ModemKind != ModemKindKeenetic {
		t.Fatalf("expected the keenetic backend by default, got %q", cfg.ModemKind)
	}
}

func TestLoadRejectsAnUnknownBackend(t *testing.T) {
	setEnv(t, map[string]string{
		"MODEM_KIND":     "zyxel",
		"MODEM_URL_BASE": "http://192.168.8.1",
	})
	if _, err := Load(); err == nil {
		t.Fatal("an unknown MODEM_KIND must be rejected")
	}
}

func TestLoadReadsTheReceiptWait(t *testing.T) {
	setEnv(t, map[string]string{
		"MODEM_KIND":                   "huawei",
		"MODEM_URL_BASE":               "http://192.168.8.1",
		"MODEM_REPORT_TIMEOUT_SECONDS": "120",
		"MODEM_REPORT_POLL_SECONDS":    "3",
	})

	cfg, err := Load()
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	if cfg.ModemReportTimeout != 120*time.Second || cfg.ModemReportPollInterval != 3*time.Second {
		t.Fatalf("unexpected receipt wait: %s / %s", cfg.ModemReportTimeout, cfg.ModemReportPollInterval)
	}
}

func TestLoadReadsTheInboxCutoff(t *testing.T) {
	// Both accepted formats: the modem wall clock (host timezone) and RFC3339.
	for _, raw := range []string{"2026-10-03 11:00:00", "2026-10-03T11:00:00+03:00"} {
		setEnv(t, map[string]string{
			"MODEM_KIND":        "huawei",
			"MODEM_URL_BASE":    "http://192.168.8.1",
			"SMS_IGNORE_BEFORE": raw,
		})

		cfg, err := Load()
		if err != nil {
			t.Fatalf("Load with %q: %v", raw, err)
		}
		if cfg.SmsIgnoreBefore.IsZero() {
			t.Fatalf("SMS_IGNORE_BEFORE %q was not applied", raw)
		}
		if !cfg.SmsIgnoreBefore.Equal(time.Date(2026, 10, 3, 11, 0, 0, 0, time.Local)) {
			t.Fatalf("SMS_IGNORE_BEFORE %q parsed to %s", raw, cfg.SmsIgnoreBefore)
		}
	}
}

func TestLoadRejectsAMalformedInboxCutoff(t *testing.T) {
	setEnv(t, map[string]string{
		"MODEM_KIND":        "huawei",
		"MODEM_URL_BASE":    "http://192.168.8.1",
		"SMS_IGNORE_BEFORE": "yesterday",
	})
	if _, err := Load(); err == nil {
		t.Fatal("a malformed SMS_IGNORE_BEFORE must be rejected")
	}
}

func TestLoadRequiresTheBaseURL(t *testing.T) {
	setEnv(t, map[string]string{"MODEM_KIND": "huawei"})
	if _, err := Load(); err == nil {
		t.Fatal("MODEM_URL_BASE must be required")
	}
}
