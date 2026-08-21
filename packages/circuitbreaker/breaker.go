package circuitbreaker

import (
	"errors"
	"time"

	gobreaker "github.com/sony/gobreaker/v2"
)

// Settings configures a provider circuit breaker.
type Settings struct {
	Name        string
	MaxFailures uint32
	CoolDown    time.Duration
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
			return err == nil
		},
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
	switch b.inner.State() {
	case gobreaker.StateOpen:
		return "open"
	case gobreaker.StateHalfOpen:
		return "half_open"
	default:
		return "closed"
	}
}
