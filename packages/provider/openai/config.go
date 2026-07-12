package openai

import "time"

const (
	defaultBaseURL        = "https://api.openai.com/v1"
	defaultRequestTimeout = 120 * time.Second
	defaultMaxRetries     = 3
	defaultRetryBaseDelay = 500 * time.Millisecond
	maxRetryBackoff       = 30 * time.Second
)

// Config tunes upstream OpenAI HTTP behavior (timeouts, retries, endpoint) for the proxy provider client.
type Config struct {
	APIKey         string
	BaseURL        string
	Timeout        time.Duration
	MaxRetries     *int
	RetryBaseDelay time.Duration
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
	if c.MaxRetries == nil {
		c.MaxRetries = intPtr(defaultMaxRetries)
	} else if *c.MaxRetries < 0 {
		c.MaxRetries = intPtr(0)
	}
	if c.RetryBaseDelay <= 0 {
		c.RetryBaseDelay = defaultRetryBaseDelay
	}
}

func (c Config) maxRetries() int {
	if c.MaxRetries == nil {
		return defaultMaxRetries
	}
	return *c.MaxRetries
}

func intPtr(v int) *int {
	return &v
}
