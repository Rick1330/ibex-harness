package anthropic

import "time"

const (
	defaultBaseURL        = "https://api.anthropic.com"
	defaultAPIVersion     = "2023-06-01"
	defaultRequestTimeout = 120 * time.Second
	defaultStreamTimeout  = 30 * time.Minute
	defaultMaxRetries     = 3
	defaultRetryBaseDelay = 500 * time.Millisecond
	defaultMaxTokens      = 4096
	maxRetryBackoff       = 30 * time.Second
	// HTTP 529 is Anthropic's overloaded_error (not in net/http constants).
	statusOverloaded = 529
)

// Config tunes upstream Anthropic HTTP behavior for the proxy provider client.
type Config struct {
	APIKey         string
	BaseURL        string
	APIVersion     string
	Timeout        time.Duration
	StreamTimeout  time.Duration
	MaxRetries     *int
	RetryBaseDelay time.Duration
	DefaultTokens  int
	// ExtraModels are additional model IDs this client accepts.
	ExtraModels []string
}

// ApplyDefaults fills zero-valued fields with production defaults.
// MaxRetries nil applies defaultMaxRetries; an explicit pointer to 0 disables retries.
func (c *Config) ApplyDefaults() {
	if c.BaseURL == "" {
		c.BaseURL = defaultBaseURL
	}
	if c.APIVersion == "" {
		c.APIVersion = defaultAPIVersion
	}
	if c.Timeout <= 0 {
		c.Timeout = defaultRequestTimeout
	}
	if c.StreamTimeout <= 0 {
		c.StreamTimeout = defaultStreamTimeout
	}
	if c.MaxRetries == nil {
		c.MaxRetries = intPtr(defaultMaxRetries)
	} else if *c.MaxRetries < 0 {
		c.MaxRetries = intPtr(0)
	}
	if c.RetryBaseDelay <= 0 {
		c.RetryBaseDelay = defaultRetryBaseDelay
	}
	if c.DefaultTokens <= 0 {
		c.DefaultTokens = defaultMaxTokens
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
