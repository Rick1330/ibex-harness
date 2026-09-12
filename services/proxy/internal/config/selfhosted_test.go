package config

import (
	"strings"
	"testing"
	"time"
)

func TestValidateSelfHostedBaseURL(t *testing.T) {
	t.Parallel()
	cases := []struct {
		name    string
		raw     string
		wantErr string
	}{
		{name: "empty", raw: "", wantErr: "required"},
		{name: "invalid", raw: "http://%", wantErr: "invalid URL"},
		{name: "bad scheme", raw: "ftp://x/v1", wantErr: "scheme"},
		{name: "userinfo", raw: "http://u:p@127.0.0.1:8000/v1", wantErr: "userinfo"},
		{name: "no host", raw: "http:///v1", wantErr: "host"},
		{name: "missing v1", raw: "http://127.0.0.1:8000", wantErr: "/v1"},
		{name: "query", raw: "http://127.0.0.1:8000/v1?x=1", wantErr: "query string"},
		{name: "fragment", raw: "http://127.0.0.1:8000/v1#frag", wantErr: "fragment"},
		{name: "ok loopback", raw: "http://127.0.0.1:8000/v1"},
		{name: "ok trailing slash", raw: "http://10.0.0.5:8000/v1/"},
		{name: "ok https hostname", raw: "https://vllm.internal/v1"},
	}
	for _, tc := range cases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			err := ValidateSelfHostedBaseURL(tc.raw)
			if tc.wantErr == "" {
				if err != nil {
					t.Fatalf("unexpected err=%v", err)
				}
				return
			}
			if err == nil || !strings.Contains(err.Error(), tc.wantErr) {
				t.Fatalf("err=%v want substring %q", err, tc.wantErr)
			}
		})
	}
}

func TestNormalizeBaseURL(t *testing.T) {
	t.Parallel()
	got := SelfHostedConfig{BaseURL: " http://127.0.0.1:8000/v1/ "}.NormalizeBaseURL()
	if got != "http://127.0.0.1:8000/v1" {
		t.Fatalf("got=%q", got)
	}
}

func TestValidateLLMConfig_SelfHostedOnlyLive(t *testing.T) {
	t.Parallel()
	cfg := Config{
		Environment: "development",
		LLMMode:     "live",
		SelfHosted: SelfHostedConfig{
			Enabled: true,
			BaseURL: "http://127.0.0.1:8000/v1",
			Models:  []string{"local"},
		},
	}
	cfg.ApplyDefaults()
	if err := cfg.validateLLMConfig(); err != nil {
		t.Fatalf("err=%v", err)
	}
}

func TestValidateLLMConfig_SelfHostedRequiresModels(t *testing.T) {
	t.Parallel()
	cfg := Config{
		LLMMode: "live",
		SelfHosted: SelfHostedConfig{
			Enabled: true,
			BaseURL: "http://127.0.0.1:8000/v1",
		},
	}
	err := cfg.validateSelfHostedConfig()
	if err == nil || !strings.Contains(err.Error(), "IBEX_SELFHOSTED_MODELS") {
		t.Fatalf("err=%v", err)
	}
}

func TestApplySelfHostedDefaults_Breaker(t *testing.T) {
	t.Parallel()
	cfg := Config{
		SelfHosted: SelfHostedConfig{Enabled: true, BaseURL: "http://127.0.0.1:8000/v1/"},
	}
	cfg.applySelfHostedDefaults()
	if cfg.SelfHosted.BaseURL != "http://127.0.0.1:8000/v1" {
		t.Fatalf("BaseURL=%q", cfg.SelfHosted.BaseURL)
	}
	if cfg.ProviderBreakerFailures != defaultBreakerFailures {
		t.Fatalf("failures=%d", cfg.ProviderBreakerFailures)
	}
	if cfg.ProviderBreakerCoolDown != defaultBreakerCoolDown {
		t.Fatalf("cool=%s", cfg.ProviderBreakerCoolDown)
	}
	if cfg.ProviderBreakerWindow != defaultBreakerWindow {
		t.Fatalf("window=%s", cfg.ProviderBreakerWindow)
	}
	if cfg.ProviderBreakerBucketPeriod != defaultBreakerBucketPeriod {
		t.Fatalf("bucket=%s", cfg.ProviderBreakerBucketPeriod)
	}
	if cfg.ProviderBreakerMinSamples != defaultBreakerMinSamples {
		t.Fatalf("min=%d", cfg.ProviderBreakerMinSamples)
	}
	if cfg.ProviderBreakerFailureRate != defaultBreakerFailureRate {
		t.Fatalf("rate=%v", cfg.ProviderBreakerFailureRate)
	}
	if cfg.SelfHosted.ReadyTimeout != defaultSelfHostedReadyTimeout {
		t.Fatalf("ready=%s", cfg.SelfHosted.ReadyTimeout)
	}
}

func TestApplyProviderBreakerRollingDefaults_PreservesExplicitEnv(t *testing.T) {
	t.Setenv("IBEX_PROVIDER_CIRCUIT_BREAKER_WINDOW_SECONDS", "0")
	t.Setenv("IBEX_PROVIDER_CIRCUIT_BREAKER_BUCKET_PERIOD_SECONDS", "-1")
	t.Setenv("IBEX_PROVIDER_CIRCUIT_BREAKER_MIN_SAMPLES", "0")
	t.Setenv("IBEX_PROVIDER_CIRCUIT_BREAKER_FAILURE_RATE", "0")

	cfg := Config{
		ProviderBreakerWindow:       durationFromEnvSeconds(0),
		ProviderBreakerBucketPeriod: durationFromEnvSeconds(-1),
		ProviderBreakerMinSamples:   0,
		ProviderBreakerFailureRate:  0,
	}
	cfg.applySelfHostedDefaults()
	if cfg.ProviderBreakerWindow != 0 {
		t.Fatalf("explicit window=0 overwritten: %s", cfg.ProviderBreakerWindow)
	}
	if cfg.ProviderBreakerBucketPeriod != -time.Second {
		t.Fatalf("explicit bucket=-1s overwritten: %s", cfg.ProviderBreakerBucketPeriod)
	}
	if cfg.ProviderBreakerMinSamples != 0 {
		t.Fatalf("explicit min_samples=0 overwritten: %d", cfg.ProviderBreakerMinSamples)
	}
	if cfg.ProviderBreakerFailureRate != 0 {
		t.Fatalf("explicit failure_rate=0 overwritten: %v", cfg.ProviderBreakerFailureRate)
	}
}

func TestDurationFromEnvSeconds(t *testing.T) {
	t.Parallel()
	if durationFromEnvSeconds(0) != 0 {
		t.Fatal("zero")
	}
	if durationFromEnvSeconds(-3) != -3*time.Second {
		t.Fatal("negative preserved")
	}
	if durationFromEnvSeconds(30) != 30*time.Second {
		t.Fatal("30s")
	}
	if durationFromEnvSeconds(9223372037) != 0 {
		t.Fatal("overflow collapses to 0")
	}
}

func TestCooldownFromSeconds(t *testing.T) {
	t.Parallel()
	if cooldownFromSeconds(0) != 0 {
		t.Fatal("zero")
	}
	if cooldownFromSeconds(30) != 30*time.Second {
		t.Fatal("30s")
	}
	if cooldownFromSeconds(9223372036) != 9223372036*time.Second {
		t.Fatal("max accepted")
	}
	if cooldownFromSeconds(9223372037) != 0 {
		t.Fatal("above max rejected")
	}
}
