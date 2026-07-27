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
	return testStorePending(t, ttl, 0)
}

func testStorePending(t *testing.T, ttl, pendingTTL time.Duration) (*RedisStore, *miniredis.Miniredis) {
	t.Helper()
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })
	return NewRedisStore(client, Config{TTL: ttl, PendingTTL: pendingTTL}), mr
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
	pendingTTL := mr.TTL(RedisKey(org, "k1"))
	if pendingTTL <= 0 || pendingTTL > store.PendingTTL()+time.Second {
		t.Fatalf("pending TTL=%v want ~= %v", pendingTTL, store.PendingTTL())
	}

	rec := Record{Fingerprint: "fp-a", Status: 200, Body: []byte(`{"ok":true}`)}
	if err := store.Commit(ctx, org, "k1", rec); err != nil {
		t.Fatalf("Commit: %v", err)
	}
	completedTTL := mr.TTL(RedisKey(org, "k1"))
	if completedTTL < time.Minute {
		t.Fatalf("completed TTL=%v want long", completedTTL)
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
	if err := s.Release(context.Background(), uuid.New(), "k"); err != nil {
		t.Fatalf("Noop Release: %v", err)
	}
}

func TestRedisStore_PendingTTLExpiresThenReclaim(t *testing.T) {
	t.Parallel()
	store, mr := testStorePending(t, time.Hour, 50*time.Millisecond)
	org := uuid.New()
	ctx := context.Background()
	if _, err := store.Claim(ctx, org, "orphan", "fp"); err != nil {
		t.Fatalf("Claim: %v", err)
	}
	mr.FastForward(100 * time.Millisecond)
	out, err := store.Claim(ctx, org, "orphan", "fp")
	if err != nil {
		t.Fatalf("Claim after expiry: %v", err)
	}
	if out.Kind != KindMiss {
		t.Fatalf("Kind=%v want Miss after pending TTL", out.Kind)
	}
}

func TestRedisStore_inspectExisting_reclaimAfterExpiry(t *testing.T) {
	t.Parallel()
	store, mr := testStorePending(t, time.Hour, time.Second)
	org := uuid.New()
	redisKey := RedisKey(org, "race")
	pending := mustEncodeRecord(pendingRecord("fp"))
	mr.Set(redisKey, pending)
	mr.SetTTL(redisKey, time.Millisecond)
	mr.FastForward(10 * time.Millisecond)
	out, err := store.inspectExisting(context.Background(), redisKey, "fp")
	if err != nil {
		t.Fatalf("inspectExisting: %v", err)
	}
	if out.Kind != KindMiss {
		t.Fatalf("Kind=%v want Miss via reclaim", out.Kind)
	}
}

func TestRedisStore_withDefaults(t *testing.T) {
	t.Parallel()
	cfg := Config{}.withDefaults()
	if cfg.TTL != defaultTTL || cfg.PendingTTL != defaultPendingTTL {
		t.Fatalf("defaults: %+v", cfg)
	}
}

func TestRedisStore_RedisDownErrors(t *testing.T) {
	t.Parallel()
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	store := NewRedisStore(client, Config{TTL: time.Hour})
	org := uuid.New()
	mr.Close()
	if _, err := store.Claim(context.Background(), org, "k", "fp"); err == nil {
		t.Fatal("expected Claim error")
	}
	if err := store.Commit(context.Background(), org, "k", Record{Fingerprint: "fp", Status: 200}); err == nil {
		t.Fatal("expected Commit error")
	}
	if err := store.Release(context.Background(), org, "k"); err == nil {
		t.Fatal("expected Release error")
	}
}

func TestRedisStore_reclaimWhenKeyExists(t *testing.T) {
	t.Parallel()
	store, mr := testStore(t, time.Hour)
	org := uuid.New()
	redisKey := RedisKey(org, "taken")
	pending := mustEncodeRecord(pendingRecord("fp"))
	mr.Set(redisKey, pending)
	out, err := store.reclaim(context.Background(), redisKey, "fp")
	if err != nil {
		t.Fatal(err)
	}
	if out.Kind != KindInProgress {
		t.Fatalf("Kind=%v want InProgress", out.Kind)
	}
}

func TestEncodeRecord_ZeroVersionDefaults(t *testing.T) {
	t.Parallel()
	raw := mustEncodeRecord(Record{State: StatePending, Fingerprint: "x"})
	rec, err := decodeRecord([]byte(raw))
	if err != nil {
		t.Fatal(err)
	}
	if rec.Version != CurrentRecordVersion {
		t.Fatalf("version=%d", rec.Version)
	}
}

func TestDecodeRecord_MissingVersion(t *testing.T) {
	t.Parallel()
	_, err := decodeRecord([]byte(`{"state":"pending","fp":"x"}`))
	if err == nil {
		t.Fatal("expected missing version error")
	}
}

func TestRedisStore_reclaimRedisDown(t *testing.T) {
	t.Parallel()
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	store := NewRedisStore(client, Config{TTL: time.Hour})
	mr.Close()
	_, err := store.reclaim(context.Background(), "idempotency:"+uuid.New().String()+":k", "fp")
	if err == nil {
		t.Fatal("expected reclaim error")
	}
}

func TestRedisStore_inspectExistingGetError(t *testing.T) {
	t.Parallel()
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	store := NewRedisStore(client, Config{TTL: time.Hour})
	org := uuid.New()
	key := "geterr"
	if _, err := store.Claim(context.Background(), org, key, "fp"); err != nil {
		t.Fatal(err)
	}
	mr.Close()
	_, err := store.Claim(context.Background(), org, key, "fp")
	if err == nil {
		t.Fatal("expected Claim error on second attempt with redis down")
	}
}

func TestRedisStore_ReleaseAllowsReclaim(t *testing.T) {
	t.Parallel()
	store, _ := testStore(t, time.Hour)
	org := uuid.New()
	ctx := context.Background()
	if _, err := store.Claim(ctx, org, "rel", "fp"); err != nil {
		t.Fatalf("Claim: %v", err)
	}
	if err := store.Release(ctx, org, "rel"); err != nil {
		t.Fatalf("Release: %v", err)
	}
	out, err := store.Claim(ctx, org, "rel", "fp")
	if err != nil {
		t.Fatalf("Claim after release: %v", err)
	}
	if out.Kind != KindMiss {
		t.Fatalf("Kind=%v want Miss", out.Kind)
	}
}

func TestRedisStore_RejectUnsupportedVersion(t *testing.T) {
	t.Parallel()
	store, mr := testStore(t, time.Hour)
	org := uuid.New()
	key := RedisKey(org, "badver")
	mr.Set(key, `{"v":99,"state":"completed","fp":"fp"}`)
	_, err := store.Claim(context.Background(), org, "badver", "fp")
	if err == nil {
		t.Fatal("expected unsupported version error")
	}
}

func TestDecodeRecord_UnsupportedVersion(t *testing.T) {
	t.Parallel()
	_, err := decodeRecord([]byte(`{"v":0,"state":"pending","fp":"x"}`))
	if err == nil {
		t.Fatal("expected error")
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
