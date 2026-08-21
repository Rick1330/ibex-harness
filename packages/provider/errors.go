package provider

import (
	"errors"
	"fmt"
	"time"
)

// ErrNoProviderForModel is returned when no registered provider supports a model.
// Callers must detect it with errors.Is(err, ErrNoProviderForModel) and map it to
// the provider-not-configured HTTP response (501 PROVIDER_NOT_CONFIGURED).
var ErrNoProviderForModel = errors.New("no provider configured for this model")

// ProviderError is returned by Complete when the provider returns a non-2xx response.
// ProviderBody may be inspected by MapError sanitizers for retry metadata only —
// never log it or copy it into client envelopes.
type ProviderError struct {
	ProviderName   string
	StatusCode     int
	ProviderBody   []byte
	ProviderErrMsg string
	RetryAfter     time.Duration
	// Reason is an optional machine-oriented cause (queue_full, circuit_open).
	Reason string
}

// Well-known ProviderError.Reason values for self-hosted backends.
const (
	ErrorReasonQueueFull   = "queue_full"
	ErrorReasonCircuitOpen = "circuit_open"
)

// Error returns a redacted, caller-safe message: provider name, HTTP status, and
// ProviderErrMsg only. ProviderBody is never included in the string.
func (e *ProviderError) Error() string {
	return fmt.Sprintf("provider %s returned %d: %s", e.ProviderName, e.StatusCode, e.ProviderErrMsg)
}
