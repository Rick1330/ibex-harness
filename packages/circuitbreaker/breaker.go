package circuitbreaker

import (
	"context"
	"errors"
	"fmt"
	"time"

	gobreaker "github.com/sony/gobreaker/v2"
)

const (
	defaultMaxFailures          = 5
	defaultCoolDown             = 30 * time.Second
	defaultMinSamples           = 10
	defaultFailureRateThreshold = 0.5
	defaultBucketPeriod         = 3 * time.Second
)

// Settings configures a provider circuit breaker.
//
// Trip mode:
//   - Window == 0 (default): consecutive-failure trip via MaxFailures (ADR-0042).
//   - Window > 0: rolling-window failure-rate trip via MinSamples + FailureRateThreshold (ADR-0076).
type Settings struct {
	Name        string
	MaxFailures uint32
	CoolDown    time.Duration

	// Rolling-window fields (opt-in). When Window > 0, ReadyToTrip uses a
	// failure-rate ratio over gobreaker's Interval/BucketPeriod counts.
	Window               time.Duration
	BucketPeriod         time.Duration
	MinSamples           uint32
	FailureRateThreshold float64

	// OnStateChange is invoked on closed/open/half_open transitions when non-nil.
	OnStateChange func(from, to string)
}

// Breaker wraps sony/gobreaker for provider Complete calls.
type Breaker struct {
	inner    *gobreaker.CircuitBreaker[any]
	coolDown time.Duration
}

// New constructs a Breaker. MaxFailures defaults to 5; CoolDown defaults to 30s.
// When Window > 0, rolling-window defaults apply (MinSamples=10, rate=0.5, BucketPeriod=3s).
func New(s Settings) (*Breaker, error) {
	s = applyBreakerDefaults(s)
	if err := validateSettings(s); err != nil {
		return nil, err
	}
	cb := gobreaker.NewCircuitBreaker[any](gobreaker.Settings{
		Name:          s.Name,
		MaxRequests:   1,
		Interval:      rollingInterval(s),
		BucketPeriod:  rollingBucketPeriod(s),
		Timeout:       s.CoolDown,
		ReadyToTrip:   readyToTrip(s),
		IsSuccessful:  isSuccessfulOutcome,
		OnStateChange: onStateChangeAdapter(s.OnStateChange),
	})
	return &Breaker{inner: cb, coolDown: s.CoolDown}, nil
}

func applyBreakerDefaults(s Settings) Settings {
	if s.Name == "" {
		s.Name = "provider"
	}
	if s.MaxFailures == 0 {
		s.MaxFailures = defaultMaxFailures
	}
	if s.CoolDown <= 0 {
		s.CoolDown = defaultCoolDown
	}
	if s.Window > 0 {
		if s.MinSamples == 0 {
			s.MinSamples = defaultMinSamples
		}
		if s.FailureRateThreshold == 0 {
			s.FailureRateThreshold = defaultFailureRateThreshold
		}
		if s.BucketPeriod == 0 {
			s.BucketPeriod = defaultBucketPeriod
		}
	}
	return s
}

func validateSettings(s Settings) error {
	if s.Window < 0 {
		return fmt.Errorf("circuitbreaker: Window must be >= 0")
	}
	if s.Window == 0 {
		if s.BucketPeriod != 0 || s.MinSamples != 0 || s.FailureRateThreshold != 0 {
			return fmt.Errorf("circuitbreaker: rolling fields require Window > 0")
		}
		return nil
	}
	if s.MinSamples == 0 {
		return fmt.Errorf("circuitbreaker: MinSamples must be > 0 when Window > 0")
	}
	if s.FailureRateThreshold <= 0 || s.FailureRateThreshold > 1 {
		return fmt.Errorf("circuitbreaker: FailureRateThreshold must be in (0, 1], got %v", s.FailureRateThreshold)
	}
	if s.BucketPeriod < 0 {
		return fmt.Errorf("circuitbreaker: BucketPeriod must be >= 0")
	}
	if s.BucketPeriod > s.Window {
		return fmt.Errorf("circuitbreaker: BucketPeriod (%s) must be <= Window (%s)", s.BucketPeriod, s.Window)
	}
	return nil
}

func rollingInterval(s Settings) time.Duration {
	if s.Window > 0 {
		return s.Window
	}
	return 0
}

func rollingBucketPeriod(s Settings) time.Duration {
	if s.Window > 0 {
		return s.BucketPeriod
	}
	return 0
}

func readyToTrip(s Settings) func(counts gobreaker.Counts) bool {
	if s.Window > 0 {
		minSamples := s.MinSamples
		threshold := s.FailureRateThreshold
		return func(counts gobreaker.Counts) bool {
			valid := validRequests(counts)
			if valid < minSamples {
				return false
			}
			return float64(counts.TotalFailures)/float64(valid) >= threshold
		}
	}
	maxFailures := s.MaxFailures
	return func(counts gobreaker.Counts) bool {
		return counts.ConsecutiveFailures >= maxFailures
	}
}

// validRequests mirrors gobreaker's unexported Counts.validRequests.
func validRequests(c gobreaker.Counts) uint32 {
	if c.Requests < c.TotalExclusions {
		return 0
	}
	return c.Requests - c.TotalExclusions
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

// Execute runs fn under the breaker. When open, returns *OpenError (errors.Is ErrOpen).
func (b *Breaker) Execute(fn func() (any, error)) (any, error) {
	if b == nil || b.inner == nil {
		return fn()
	}
	out, err := b.inner.Execute(fn)
	if isBreakerBlocked(err) {
		return nil, &OpenError{RetryAfter: b.coolDown}
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

// CoolDown returns the configured open-state timeout used for Retry-After.
func (b *Breaker) CoolDown() time.Duration {
	if b == nil {
		return 0
	}
	return b.coolDown
}
