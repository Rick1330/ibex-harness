package circuitbreaker

import (
	"context"
	"errors"
	"strings"
	"sync"
	"testing"
	"time"
)

func TestBreaker_OpensAfterConsecutiveFailures(t *testing.T) {
	t.Parallel()
	b := New(Settings{Name: "t", MaxFailures: 2, CoolDown: time.Minute})
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
	assertState(t, b, "open")
}

func TestBreaker_DefaultsAndNilExecute(t *testing.T) {
	t.Parallel()
	b := New(Settings{})
	assertState(t, b, "closed")
	out, err := (*Breaker)(nil).Execute(func() (any, error) { return 7, nil })
	if err != nil || out.(int) != 7 {
		t.Fatalf("nil breaker: %v %v", out, err)
	}
	if (*Breaker)(nil).State() != "closed" {
		t.Fatal("nil state")
	}
}

func TestBreaker_CanceledDoesNotTrip(t *testing.T) {
	t.Parallel()
	b := New(Settings{Name: "t", MaxFailures: 1, CoolDown: time.Minute})
	_, err := b.Execute(func() (any, error) { return nil, context.Canceled })
	if !errors.Is(err, context.Canceled) {
		t.Fatalf("err=%v", err)
	}
	assertState(t, b, "closed")
	_, err = b.Execute(func() (any, error) { return "ok", nil })
	if err != nil {
		t.Fatalf("err=%v", err)
	}
}

func TestBreaker_RecoversAfterCoolDown(t *testing.T) {
	t.Parallel()
	b := New(Settings{Name: "t", MaxFailures: 1, CoolDown: 25 * time.Millisecond})
	_, _ = b.Execute(func() (any, error) { return nil, errors.New("fail") })
	assertState(t, b, "open")
	time.Sleep(40 * time.Millisecond)
	out, err := b.Execute(func() (any, error) { return "ok", nil })
	if err != nil {
		t.Fatalf("err=%v", err)
	}
	if out.(string) != "ok" {
		t.Fatalf("out=%v", out)
	}
	assertState(t, b, "closed")
}

func TestBreaker_OnStateChange(t *testing.T) {
	t.Parallel()
	var mu sync.Mutex
	var transitions []string
	b := New(Settings{
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

func assertState(t *testing.T, b *Breaker, want string) {
	t.Helper()
	if got := b.State(); got != want {
		t.Fatalf("state=%s want %s", got, want)
	}
}
