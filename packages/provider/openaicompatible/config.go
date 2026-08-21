package openaicompatible

import "time"

const (
	defaultRequestTimeout = 120 * time.Second
	defaultStreamTimeout  = 30 * time.Minute
	defaultMaxRetries     = 3
	defaultRetryBaseDelay = 500 * time.Millisecond
	maxRetryBackoff       = 30 * time.Second

	// ProviderNameSelfHosted is the Registry / metrics name for the self-hosted adapter.
	ProviderNameSelfHosted = "openaicompatible"
	// ProviderNameOpenAI is the Registry / metrics name for hosted OpenAI.
	ProviderNameOpenAI = "openai"
)

// AuthMode controls Authorization header behavior.
type AuthMode int

const (
	// AuthBearerAlways always sends Authorization: Bearer {key} (hosted OpenAI).
	AuthBearerAlways AuthMode = iota
	// AuthBearerOmitEmpty omits Authorization when APIKey is empty (typical vLLM/Ollama).
	AuthBearerOmitEmpty
)

// Config tunes an OpenAI-compatible chat completions client.
type Config struct {
	// ProviderName is returned by Name() and used in metrics/spans (required).
	ProviderName   string
	APIKey         string
	BaseURL        string
	Timeout        time.Duration
	StreamTimeout  time.Duration
	MaxRetries     *int
	RetryBaseDelay time.Duration
	// BuiltInModels are always on the allowlist (hosted OpenAI curated IDs).
	BuiltInModels []string
	// ExtraModels extend the allowlist (ExtraModels / IBEX_SELFHOSTED_MODELS).
	ExtraModels []string
	AuthMode    AuthMode
	// Breaker, when non-nil, wraps each Complete attempt (self-hosted path).
	Breaker Breaker
}

// Breaker is the circuit-breaker surface used by the self-hosted adapter.
type Breaker interface {
	Execute(func() (any, error)) (any, error)
}

// ApplyDefaults fills zero-valued fields. ProviderName and BaseURL must be set by caller.
func (c *Config) ApplyDefaults() {
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
}

func (c Config) maxRetries() int {
	if c.MaxRetries == nil {
		return defaultMaxRetries
	}
	return *c.MaxRetries
}

func intPtr(v int) *int { return &v }
