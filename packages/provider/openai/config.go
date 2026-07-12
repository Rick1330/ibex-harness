package openai

import "time"

const (
	defaultBaseURL        = "https://api.openai.com/v1"
	defaultRequestTimeout = 120 * time.Second
	defaultMaxRetries     = 3
	defaultRetryBaseDelay = 500 * time.Millisecond
	maxRetryBackoff       = 30 * time.Second
)

// Config holds OpenAI client configuration.
type Config struct {
	APIKey         string
	BaseURL        string
	Timeout        time.Duration
	MaxRetries     int
	RetryBaseDelay time.Duration
}

// ApplyDefaults fills zero-valued fields with production defaults.
func (c *Config) ApplyDefaults() {
	if c.BaseURL == "" {
		c.BaseURL = defaultBaseURL
	}
	if c.Timeout <= 0 {
		c.Timeout = defaultRequestTimeout
	}
	if c.MaxRetries < 0 {
		c.MaxRetries = 0
	}
	if c.MaxRetries == 0 {
		c.MaxRetries = defaultMaxRetries
	}
	if c.RetryBaseDelay <= 0 {
		c.RetryBaseDelay = defaultRetryBaseDelay
	}
}
