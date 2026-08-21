package circuitbreaker

import (
	"errors"
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
	if b.State() != "open" {
		t.Fatalf("state=%s", b.State())
	}
}

func TestBreaker_DefaultsAndNilExecute(t *testing.T) {
	t.Parallel()
	b := New(Settings{})
	if b.State() != "closed" {
		t.Fatalf("state=%s", b.State())
	}
	out, err := (*Breaker)(nil).Execute(func() (any, error) { return 7, nil })
	if err != nil || out.(int) != 7 {
		t.Fatalf("nil breaker: %v %v", out, err)
	}
	if (*Breaker)(nil).State() != "closed" {
		t.Fatal("nil state")
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

func assertState(t *testing.T, b *Breaker, want string) {
	t.Helper()
	if got := b.State(); got != want {
		t.Fatalf("state=%s want %s", got, want)
	}
}
