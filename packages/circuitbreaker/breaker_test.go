package circuitbreaker

import (
	"context"
	"errors"
	"math"
	"strings"
	"sync"
	"testing"
	"time"
)

func mustNew(t *testing.T, s Settings) *Breaker {
	t.Helper()
	b, err := New(s)
	if err != nil {
		t.Fatalf("New: %v", err)
	}
	return b
}

func TestBreaker_OpensAfterConsecutiveFailures(t *testing.T) {
	t.Parallel()
	b := mustNew(t, Settings{Name: "t", MaxFailures: 2, CoolDown: time.Minute})
	fail := errors.New("boom")
	for i := 0; i < 2; i++ {
		_, err := b.Execute(func() (any, error) { return nil, fail })
		if !errors.Is(err, fail) {
			t.Fatalf("err=%v", err)
		}
	}
	_, err := b.Execute(func() (any, error) { return "ok", nil })
	if !errors.Is(err, ErrOpen) {
		t.Fatalf("err=%v want ErrOpen", err)
	}
	var oe *OpenError
	if !errors.As(err, &oe) || oe.RetryAfter != time.Minute {
		t.Fatalf("OpenError RetryAfter=%v want %v", oe, time.Minute)
	}
	assertState(t, b, "open")
}

func TestBreaker_DefaultsAndNilExecute(t *testing.T) {
	t.Parallel()
	b := mustNew(t, Settings{})
	assertState(t, b, "closed")
	out, err := (*Breaker)(nil).Execute(func() (any, error) { return 7, nil })
	if err != nil || out.(int) != 7 {
		t.Fatalf("nil breaker: %v %v", out, err)
	}
	if (*Breaker)(nil).State() != "closed" {
		t.Fatal("nil state")
	}
	if (*Breaker)(nil).CoolDown() != 0 {
		t.Fatal("nil CoolDown")
	}
	if b.CoolDown() != defaultCoolDown {
		t.Fatalf("CoolDown=%s", b.CoolDown())
	}
}

func TestBreaker_CanceledDoesNotTrip(t *testing.T) {
	t.Parallel()
	assertNonFailureDoesNotTrip(t, context.Canceled)
}

func TestBreaker_DeadlineExceededDoesNotTrip(t *testing.T) {
	t.Parallel()
	assertNonFailureDoesNotTrip(t, context.DeadlineExceeded)
}

func assertNonFailureDoesNotTrip(t *testing.T, nonFailure error) {
	t.Helper()
	b := mustNew(t, Settings{Name: "t", MaxFailures: 1, CoolDown: time.Minute})
	_, err := b.Execute(func() (any, error) { return nil, nonFailure })
	if !errors.Is(err, nonFailure) {
		t.Fatalf("err=%v want %v", err, nonFailure)
	}
	assertState(t, b, "closed")
	_, err = b.Execute(func() (any, error) { return "ok", nil })
	if err != nil {
		t.Fatalf("err=%v", err)
	}
}

func TestBreaker_RecoversAfterCoolDown(t *testing.T) {
	t.Parallel()
	b := mustNew(t, Settings{Name: "t", MaxFailures: 1, CoolDown: 25 * time.Millisecond})
	_, _ = b.Execute(func() (any, error) { return nil, errors.New("fail") })
	assertState(t, b, "open")
	time.Sleep(40 * time.Millisecond)
	out, err := b.Execute(func() (any, error) { return "ok", nil })
	if err != nil {
		t.Fatalf("err=%v", err)
	}
	got, ok := out.(string)
	if !ok || got != "ok" {
		t.Fatalf("out=%v", out)
	}
	assertState(t, b, "closed")
}

func TestBreaker_OnStateChange(t *testing.T) {
	t.Parallel()
	var mu sync.Mutex
	var transitions []string
	b := mustNew(t, Settings{
		Name:        "t",
		MaxFailures: 1,
		CoolDown:    25 * time.Millisecond,
		OnStateChange: func(from, to string) {
			mu.Lock()
			transitions = append(transitions, from+"->"+to)
			mu.Unlock()
		},
	})
	_, _ = b.Execute(func() (any, error) { return nil, errors.New("fail") })
	time.Sleep(40 * time.Millisecond)
	_, _ = b.Execute(func() (any, error) { return "ok", nil })

	mu.Lock()
	defer mu.Unlock()
	joined := ""
	for _, tr := range transitions {
		joined += tr + ";"
	}
	if !strings.Contains(joined, "closed->open") {
		t.Fatalf("transitions=%v", transitions)
	}
}

func TestBreaker_RollingTripsAtThreshold(t *testing.T) {
	t.Parallel()
	b := mustNew(t, Settings{
		Name:                 "roll",
		Window:               time.Minute,
		BucketPeriod:         time.Minute, // single bucket = fixed window
		MinSamples:           4,
		FailureRateThreshold: 0.5,
		CoolDown:             time.Minute,
	})
	fail := errors.New("boom")
	// Two successes then two failures → exactly 50% at MinSamples=4; trip on 2nd failure.
	for i := 0; i < 2; i++ {
		_, err := b.Execute(func() (any, error) { return "ok", nil })
		if err != nil {
			t.Fatalf("success %d: %v", i, err)
		}
		assertState(t, b, "closed")
	}
	_, err := b.Execute(func() (any, error) { return nil, fail })
	if !errors.Is(err, fail) {
		t.Fatalf("first failure: %v", err)
	}
	assertState(t, b, "closed") // 1/3 < floor of 4 samples
	_, err = b.Execute(func() (any, error) { return nil, fail })
	if !errors.Is(err, fail) {
		t.Fatalf("second failure (exact 50%%): %v", err)
	}
	assertState(t, b, "open")
	_, err = b.Execute(func() (any, error) { return "ok", nil })
	if !errors.Is(err, ErrOpen) {
		t.Fatalf("err=%v want ErrOpen", err)
	}
}

func TestBreaker_RollingDoesNotTripBeforeMinSamples(t *testing.T) {
	t.Parallel()
	b := mustNew(t, Settings{
		Name:                 "floor",
		Window:               time.Minute,
		BucketPeriod:         time.Minute,
		MinSamples:           10,
		FailureRateThreshold: 0.5,
		CoolDown:             time.Minute,
	})
	fail := errors.New("boom")
	for i := 0; i < 9; i++ {
		_, err := b.Execute(func() (any, error) { return nil, fail })
		if !errors.Is(err, fail) {
			t.Fatalf("i=%d err=%v", i, err)
		}
		assertState(t, b, "closed")
	}
	_, err := b.Execute(func() (any, error) { return nil, fail })
	if !errors.Is(err, fail) {
		t.Fatalf("10th err=%v", err)
	}
	assertState(t, b, "open")
}

func TestBreaker_RollingResetsAcrossWindow(t *testing.T) {
	t.Parallel()
	window := 40 * time.Millisecond
	b := mustNew(t, Settings{
		Name:                 "decay",
		Window:               window,
		BucketPeriod:         window, // fixed window clear
		MinSamples:           3,
		FailureRateThreshold: 0.5,
		CoolDown:             time.Minute,
	})
	fail := errors.New("boom")
	for i := 0; i < 2; i++ {
		_, _ = b.Execute(func() (any, error) { return nil, fail })
	}
	assertState(t, b, "closed") // below MinSamples
	time.Sleep(window + 20*time.Millisecond)
	// New generation: prior-window failures must not count toward MinSamples.
	for i := 0; i < 2; i++ {
		_, err := b.Execute(func() (any, error) { return nil, fail })
		if !errors.Is(err, fail) {
			t.Fatalf("new-window fail %d: %v", i, err)
		}
	}
	assertState(t, b, "closed") // only 2 samples in the new window
	_, err := b.Execute(func() (any, error) { return "ok", nil })
	if err != nil {
		t.Fatalf("success while closed: %v", err)
	}
}

func TestBreaker_DualModeCoexistence(t *testing.T) {
	t.Parallel()
	consec := mustNew(t, Settings{Name: "consec", MaxFailures: 2, CoolDown: time.Minute})
	rolling := mustNew(t, Settings{
		Name:                 "rolling",
		Window:               time.Minute,
		BucketPeriod:         time.Minute,
		MinSamples:           10,
		FailureRateThreshold: 0.5,
		CoolDown:             time.Minute,
	})
	fail := errors.New("boom")

	var wg sync.WaitGroup
	wg.Add(2)
	go func() {
		defer wg.Done()
		for i := 0; i < 2; i++ {
			_, _ = consec.Execute(func() (any, error) { return nil, fail })
		}
	}()
	go func() {
		defer wg.Done()
		for i := 0; i < 5; i++ {
			_, _ = rolling.Execute(func() (any, error) { return nil, fail })
		}
	}()
	wg.Wait()

	assertState(t, consec, "open")
	assertState(t, rolling, "closed") // 5 < MinSamples 10
	_, err := rolling.Execute(func() (any, error) { return "ok", nil })
	if err != nil {
		t.Fatalf("rolling still closed path: %v", err)
	}
	_, err = consec.Execute(func() (any, error) { return "ok", nil })
	if !errors.Is(err, ErrOpen) {
		t.Fatalf("consec open: %v", err)
	}
}

func TestBreaker_RollingExcludesCanceled(t *testing.T) {
	t.Parallel()
	b := mustNew(t, Settings{
		Name: "excl", Window: time.Minute, BucketPeriod: time.Minute,
		MinSamples: 2, FailureRateThreshold: 0.5, CoolDown: time.Minute,
	})
	for i := 0; i < 5; i++ {
		_, err := b.Execute(func() (any, error) { return nil, context.Canceled })
		if !errors.Is(err, context.Canceled) {
			t.Fatalf("err=%v", err)
		}
	}
	assertState(t, b, "closed")
}

func TestBreaker_ValidateRejectsPartialRolling(t *testing.T) {
	t.Parallel()
	_, err := New(Settings{Name: "bad", MinSamples: 10})
	if err == nil {
		t.Fatal("want error for MinSamples without Window")
	}
	_, err = New(Settings{Name: "bad", Window: time.Second, FailureRateThreshold: 1.5, MinSamples: 1})
	if err == nil {
		t.Fatal("want error for rate > 1")
	}
	_, err = New(Settings{
		Name: "bad", Window: time.Second, FailureRateThreshold: math.NaN(), MinSamples: 1,
	})
	if err == nil {
		t.Fatal("want error for NaN rate")
	}
	_, err = New(Settings{
		Name: "bad", Window: time.Second, BucketPeriod: 2 * time.Second,
		MinSamples: 1, FailureRateThreshold: 0.5,
	})
	if err == nil {
		t.Fatal("want error for BucketPeriod > Window")
	}
}

func TestBreaker_ConcurrentExecute(t *testing.T) {
	t.Parallel()
	b := mustNew(t, Settings{Name: "race", MaxFailures: 100, CoolDown: time.Minute})
	var wg sync.WaitGroup
	for i := 0; i < 32; i++ {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			_, _ = b.Execute(func() (any, error) {
				if i%2 == 0 {
					return "ok", nil
				}
				return nil, errors.New("fail")
			})
		}(i)
	}
	wg.Wait()
	_ = b.State()
}

func assertState(t *testing.T, b *Breaker, want string) {
	t.Helper()
	if got := b.State(); got != want {
		t.Fatalf("state=%s want %s", got, want)
	}
}
