package config

import (
	"fmt"
	"net/url"
	"strings"
	"time"
)

const (
	defaultSelfHostedReadyTimeout  = 60 * time.Second
	defaultSelfHostedReadyInterval = 2 * time.Second
	defaultBreakerFailures         = 5
	defaultBreakerCoolDown         = 30 * time.Second
)

// SelfHostedConfig holds OpenAI-compatible self-hosted backend settings (vLLM-first).
type SelfHostedConfig struct {
	Enabled      bool
	BaseURL      string
	APIKey       string
	Models       []string
	ReadyTimeout time.Duration
	ReadyPoll    time.Duration
	// BreakerFailures trips after this many consecutive failures (0 = default).
	BreakerFailures uint32
	BreakerCoolDown time.Duration
}

// ValidateSelfHostedBaseURL enforces http(s), no userinfo, path ending in /v1.
// Private/loopback hosts are allowed when self-hosted is explicitly enabled
// (documented SSRF exception for air-gapped backends).
func ValidateSelfHostedBaseURL(raw string) error {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return fmt.Errorf("IBEX_SELFHOSTED_BASE_URL is required when IBEX_SELFHOSTED_ENABLED=true")
	}
	u, err := url.Parse(raw)
	if err != nil {
		return fmt.Errorf("IBEX_SELFHOSTED_BASE_URL: invalid URL: %w", err)
	}
	if err := requireHTTPSchemeAndHost(u); err != nil {
		return err
	}
	if err := rejectDisallowedURLParts(u); err != nil {
		return err
	}
	path := strings.TrimSuffix(u.Path, "/")
	if !strings.HasSuffix(path, "/v1") {
		return fmt.Errorf("IBEX_SELFHOSTED_BASE_URL: path must end with /v1 (got %q)", u.Path)
	}
	return nil
}

func requireHTTPSchemeAndHost(u *url.URL) error {
	if u.Scheme != "http" && u.Scheme != "https" {
		return fmt.Errorf("IBEX_SELFHOSTED_BASE_URL: scheme must be http or https")
	}
	if strings.TrimSpace(u.Host) == "" {
		return fmt.Errorf("IBEX_SELFHOSTED_BASE_URL: host is required")
	}
	return nil
}

func rejectDisallowedURLParts(u *url.URL) error {
	if u.User != nil {
		return fmt.Errorf("IBEX_SELFHOSTED_BASE_URL: userinfo is not allowed")
	}
	if u.RawQuery != "" {
		return fmt.Errorf("IBEX_SELFHOSTED_BASE_URL: query string is not allowed")
	}
	if u.Fragment != "" {
		return fmt.Errorf("IBEX_SELFHOSTED_BASE_URL: fragment is not allowed")
	}
	return nil
}

func (c SelfHostedConfig) NormalizeBaseURL() string {
	return strings.TrimRight(strings.TrimSpace(c.BaseURL), "/")
}
