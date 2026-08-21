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
	c.applyEndpointDefaults()
	c.applyTimeoutDefaults()
	c.applyRetryDefaults()
	c.applyTokenDefaults()
}

func (c *Config) applyEndpointDefaults() {
	if c.BaseURL == "" {
		c.BaseURL = defaultBaseURL
	}
	if c.APIVersion == "" {
		c.APIVersion = defaultAPIVersion
	}
}

func (c *Config) applyTimeoutDefaults() {
	if c.Timeout <= 0 {
		c.Timeout = defaultRequestTimeout
	}
	if c.StreamTimeout <= 0 {
		c.StreamTimeout = defaultStreamTimeout
	}
}

func (c *Config) applyRetryDefaults() {
	switch {
	case c.MaxRetries == nil:
		c.MaxRetries = intPtr(defaultMaxRetries)
	case *c.MaxRetries < 0:
		c.MaxRetries = intPtr(0)
	}
	if c.RetryBaseDelay <= 0 {
		c.RetryBaseDelay = defaultRetryBaseDelay
	}
}

func (c *Config) applyTokenDefaults() {
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
