package idempotency

import (
	"context"
	"sync"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
)

func testStore(t *testing.T, ttl time.Duration) (*RedisStore, *miniredis.Miniredis) {
	t.Helper()
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })
	return NewRedisStore(client, Config{TTL: ttl}), mr
}

func TestRedisStore_ClaimMissThenCommitHit(t *testing.T) {
	t.Parallel()
	store, mr := testStore(t, time.Hour)
	org := uuid.MustParse("550e8400-e29b-41d4-a716-446655440000")
	ctx := context.Background()

	out, err := store.Claim(ctx, org, "k1", "fp-a")
	if err != nil {
		t.Fatalf("Claim: %v", err)
	}
	if out.Kind != KindMiss {
		t.Fatalf("Kind=%v want Miss", out.Kind)
	}
	if !mr.Exists(RedisKey(org, "k1")) {
		t.Fatal("expected pending key")
	}
	ttl := mr.TTL(RedisKey(org, "k1"))
	if ttl <= 0 {
		t.Fatalf("TTL=%v want >0", ttl)
	}

	rec := Record{Fingerprint: "fp-a", Status: 200, Body: []byte(`{"ok":true}`)}
	if err := store.Commit(ctx, org, "k1", rec); err != nil {
		t.Fatalf("Commit: %v", err)
	}

	out, err = store.Claim(ctx, org, "k1", "fp-a")
	if err != nil {
		t.Fatalf("Claim after commit: %v", err)
	}
	if out.Kind != KindHit {
		t.Fatalf("Kind=%v want Hit", out.Kind)
	}
	if out.Record.Status != 200 || string(out.Record.Body) != `{"ok":true}` {
		t.Fatalf("record=%+v", out.Record)
	}
}

func TestRedisStore_SameKeyDifferentFingerprintConflict(t *testing.T) {
	t.Parallel()
	store, _ := testStore(t, time.Hour)
	org := uuid.New()
	ctx := context.Background()

	if _, err := store.Claim(ctx, org, "same", "fp-1"); err != nil {
		t.Fatalf("Claim: %v", err)
	}
	if err := store.Commit(ctx, org, "same", Record{Fingerprint: "fp-1", Status: 200, Body: []byte(`a`)}); err != nil {
		t.Fatalf("Commit: %v", err)
	}
	out, err := store.Claim(ctx, org, "same", "fp-2")
	if err != nil {
		t.Fatalf("Claim: %v", err)
	}
	if out.Kind != KindConflict {
		t.Fatalf("Kind=%v want Conflict", out.Kind)
	}
}

func TestRedisStore_InProgress(t *testing.T) {
	t.Parallel()
	store, _ := testStore(t, time.Hour)
	org := uuid.New()
	ctx := context.Background()

	if _, err := store.Claim(ctx, org, "inflight", "fp"); err != nil {
		t.Fatalf("Claim: %v", err)
	}
	out, err := store.Claim(ctx, org, "inflight", "fp")
	if err != nil {
		t.Fatalf("second Claim: %v", err)
	}
	if out.Kind != KindInProgress {
		t.Fatalf("Kind=%v want InProgress", out.Kind)
	}
}

func TestRedisStore_CrossOrgIsolation(t *testing.T) {
	t.Parallel()
	store, _ := testStore(t, time.Hour)
	orgA, orgB := uuid.New(), uuid.New()
	ctx := context.Background()

	if _, err := store.Claim(ctx, orgA, "shared-key", "fp"); err != nil {
		t.Fatalf("Claim A: %v", err)
	}
	out, err := store.Claim(ctx, orgB, "shared-key", "fp")
	if err != nil {
		t.Fatalf("Claim B: %v", err)
	}
	if out.Kind != KindMiss {
		t.Fatalf("org B Kind=%v want Miss", out.Kind)
	}
}

func TestRedisStore_ConcurrentClaim(t *testing.T) {
	t.Parallel()
	store, _ := testStore(t, time.Hour)
	org := uuid.New()
	ctx := context.Background()

	const n = 20
	kinds := make([]Kind, n)
	var wg sync.WaitGroup
	wg.Add(n)
	for i := 0; i < n; i++ {
		i := i
		go func() {
			defer wg.Done()
			out, err := store.Claim(ctx, org, "race", "fp")
			if err != nil {
				t.Errorf("Claim: %v", err)
				return
			}
			kinds[i] = out.Kind
		}()
	}
	wg.Wait()

	misses, inProg := 0, 0
	for _, k := range kinds {
		switch k {
		case KindMiss:
			misses++
		case KindInProgress:
			inProg++
		default:
			t.Fatalf("unexpected kind %v", k)
		}
	}
	if misses != 1 {
		t.Fatalf("misses=%d want 1", misses)
	}
	if inProg != n-1 {
		t.Fatalf("in_progress=%d want %d", inProg, n-1)
	}
}

func TestRedisStore_ClaimCanceledContext(t *testing.T) {
	t.Parallel()
	store, _ := testStore(t, time.Hour)
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	_, err := store.Claim(ctx, uuid.New(), "k", "fp")
	if err == nil {
		t.Fatal("expected error on canceled ctx")
	}
}

func TestNoop_AlwaysMiss(t *testing.T) {
	t.Parallel()
	s := Noop()
	out, err := s.Claim(context.Background(), uuid.New(), "k", "fp")
	if err != nil || out.Kind != KindMiss {
		t.Fatalf("Noop Claim: %+v %v", out, err)
	}
	if err := s.Commit(context.Background(), uuid.New(), "k", Record{}); err != nil {
		t.Fatalf("Noop Commit: %v", err)
	}
}

func TestRedisKey_Format(t *testing.T) {
	t.Parallel()
	org := uuid.MustParse("550e8400-e29b-41d4-a716-446655440000")
	got := RedisKey(org, "abc")
	want := "idempotency:550e8400-e29b-41d4-a716-446655440000:abc"
	if got != want {
		t.Fatalf("got %q want %q", got, want)
	}
}
