package circuitbreaker

import (
	"errors"
	"time"
)

// ErrOpen is returned when the circuit is open and the call was not attempted.
var ErrOpen = errors.New("circuit breaker open")

// OpenError is returned when the breaker rejects a call. It wraps ErrOpen and
// carries the configured CoolDown for Retry-After mapping.
type OpenError struct {
	RetryAfter time.Duration
}

// Error implements the error interface.
func (e *OpenError) Error() string {
	return ErrOpen.Error()
}

// Is reports whether target is ErrOpen.
func (e *OpenError) Is(target error) bool {
	return target == ErrOpen
}
