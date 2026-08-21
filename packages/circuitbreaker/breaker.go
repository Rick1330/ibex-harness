package circuitbreaker

import (
	"context"
	"errors"
	"time"

	gobreaker "github.com/sony/gobreaker/v2"
)

// Settings configures a provider circuit breaker.
type Settings struct {
	Name        string
	MaxFailures uint32
	CoolDown    time.Duration
	// OnStateChange is invoked on closed/open/half_open transitions when non-nil.
	OnStateChange func(from, to string)
}

// Breaker wraps sony/gobreaker for provider Complete calls.
type Breaker struct {
	inner *gobreaker.CircuitBreaker[any]
}

// New constructs a Breaker. MaxFailures defaults to 5; CoolDown defaults to 30s.
func New(s Settings) *Breaker {
	s = applyBreakerDefaults(s)
	cb := gobreaker.NewCircuitBreaker[any](gobreaker.Settings{
		Name:        s.Name,
		MaxRequests: 1,
		Interval:    0,
		Timeout:     s.CoolDown,
		ReadyToTrip: func(counts gobreaker.Counts) bool {
			return counts.ConsecutiveFailures >= s.MaxFailures
		},
		IsSuccessful: func(err error) bool {
			return isSuccessfulOutcome(err)
		},
		OnStateChange: onStateChangeAdapter(s.OnStateChange),
	})
	return &Breaker{inner: cb}
}

func applyBreakerDefaults(s Settings) Settings {
	if s.Name == "" {
		s.Name = "provider"
	}
	if s.MaxFailures == 0 {
		s.MaxFailures = 5
	}
	if s.CoolDown <= 0 {
		s.CoolDown = 30 * time.Second
	}
	return s
}

func isSuccessfulOutcome(err error) bool {
	if err == nil {
		return true
	}
	return errors.Is(err, context.Canceled) || errors.Is(err, context.DeadlineExceeded)
}

func onStateChangeAdapter(cb func(from, to string)) func(name string, from gobreaker.State, to gobreaker.State) {
	if cb == nil {
		return nil
	}
	return func(_ string, from, to gobreaker.State) {
		cb(stateString(from), stateString(to))
	}
}

func stateString(s gobreaker.State) string {
	switch s {
	case gobreaker.StateOpen:
		return "open"
	case gobreaker.StateHalfOpen:
		return "half_open"
	default:
		return "closed"
	}
}

// Execute runs fn under the breaker. When open, returns ErrOpen.
func (b *Breaker) Execute(fn func() (any, error)) (any, error) {
	if b == nil || b.inner == nil {
		return fn()
	}
	out, err := b.inner.Execute(fn)
	if isBreakerBlocked(err) {
		return nil, ErrOpen
	}
	return out, err
}

func isBreakerBlocked(err error) bool {
	return errors.Is(err, gobreaker.ErrOpenState) || errors.Is(err, gobreaker.ErrTooManyRequests)
}

// State returns a stable string for metrics/logs.
func (b *Breaker) State() string {
	if b == nil || b.inner == nil {
		return "closed"
	}
	return stateString(b.inner.State())
}
