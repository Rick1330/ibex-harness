package openai

import "time"

const (
	defaultBaseURL        = "https://api.openai.com/v1"
	defaultRequestTimeout = 120 * time.Second
	defaultStreamTimeout  = 30 * time.Minute
	defaultMaxRetries     = 3
	defaultRetryBaseDelay = 500 * time.Millisecond
)

// Config tunes upstream OpenAI HTTP behavior (timeouts, retries, endpoint) for the proxy provider client.
type Config struct {
	APIKey         string
	BaseURL        string
	Timeout        time.Duration
	StreamTimeout  time.Duration
	MaxRetries     *int
	RetryBaseDelay time.Duration
	// ExtraModels are additional model IDs this client accepts (e.g. OpenRouter slugs).
	ExtraModels []string
}

// ApplyDefaults fills zero-valued fields with production defaults.
// MaxRetries nil applies defaultMaxRetries; an explicit pointer to 0 disables retries.
func (c *Config) ApplyDefaults() {
	if c.BaseURL == "" {
		c.BaseURL = defaultBaseURL
	}
	if c.Timeout <= 0 {
		c.Timeout = defaultRequestTimeout
	}
	if c.StreamTimeout <= 0 {
		c.StreamTimeout = defaultStreamTimeout
	}
	if c.MaxRetries == nil {
		v := defaultMaxRetries
		c.MaxRetries = &v
	} else if *c.MaxRetries < 0 {
		v := 0
		c.MaxRetries = &v
	}
	if c.RetryBaseDelay <= 0 {
		c.RetryBaseDelay = defaultRetryBaseDelay
	}
}

// Metrics records upstream provider outcomes and retries.
type Metrics interface {
	IncProviderRequest(provider, statusClass string)
	IncProviderRetry(provider string)
}
