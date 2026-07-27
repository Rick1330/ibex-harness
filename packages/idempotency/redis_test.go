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

func tok(org uuid.UUID, key string) Token {
	return Token{OrgID: org, Key: key}
}

func mustEncode(t *testing.T, rec Record) string {
	t.Helper()
	raw, err := encodeRecord(rec)
	if err != nil {
		t.Fatalf("encode: %v", err)
	}
	return raw
}

type claimCall struct {
	store Store
	tkn   Token
	fp    Fingerprint
}

func mustClaim(t *testing.T, ctx context.Context, call claimCall) Outcome {
	t.Helper()
	out, err := call.store.Claim(ctx, call.tkn, call.fp)
	if err != nil {
		t.Fatalf("Claim: %v", err)
	}
	return out
}

func requireKind(t *testing.T, got, want Kind) {
	t.Helper()
	if got != want {
		t.Fatalf("Kind=%v want %v", got, want)
	}
}

func TestRedisStore_ClaimMissThenCommitHit(t *testing.T) {
	t.Parallel()
	store, mr := testStore(t, time.Hour)
	org := uuid.MustParse("550e8400-e29b-41d4-a716-446655440000")
	ctx := context.Background()
	tkn := tok(org, "k1")

	out := mustClaim(t, ctx, claimCall{store: store, tkn: tkn, fp: "fp-a"})
	requireKind(t, out.Kind, KindMiss)
	assertPendingTTL(t, mr, tkn, store.PendingTTL())

	rec := Record{Fingerprint: "fp-a", Status: 200, Body: []byte(`{"ok":true}`)}
	if err := store.Commit(ctx, tkn, rec); err != nil {
		t.Fatalf("Commit: %v", err)
	}
	assertLongTTL(t, mr, tkn)

	out = mustClaim(t, ctx, claimCall{store: store, tkn: tkn, fp: "fp-a"})
	requireKind(t, out.Kind, KindHit)
	if out.Record.Status != 200 || string(out.Record.Body) != `{"ok":true}` {
		t.Fatalf("record=%+v", out.Record)
	}
}

func assertPendingTTL(t *testing.T, mr *miniredis.Miniredis, tkn Token, want time.Duration) {
	t.Helper()
	if !mr.Exists(RedisKey(tkn)) {
		t.Fatal("expected pending key")
	}
	got := mr.TTL(RedisKey(tkn))
	if got <= 0 || got > want+time.Second {
		t.Fatalf("pending TTL=%v want ~= %v", got, want)
	}
}

func assertLongTTL(t *testing.T, mr *miniredis.Miniredis, tkn Token) {
	t.Helper()
	if mr.TTL(RedisKey(tkn)) < time.Minute {
		t.Fatalf("completed TTL=%v want long", mr.TTL(RedisKey(tkn)))
	}
}

func TestRedisStore_SameKeyDifferentFingerprintConflict(t *testing.T) {
	t.Parallel()
	store, _ := testStore(t, time.Hour)
	ctx := context.Background()
	tkn := tok(uuid.New(), "same")
	_ = mustClaim(t, ctx, claimCall{store: store, tkn: tkn, fp: "fp-1"})
	if err := store.Commit(ctx, tkn, Record{Fingerprint: "fp-1", Status: 200, Body: []byte(`a`)}); err != nil {
		t.Fatalf("Commit: %v", err)
	}
	requireKind(t, mustClaim(t, ctx, claimCall{store: store, tkn: tkn, fp: "fp-2"}).Kind, KindConflict)
}

func TestRedisStore_InProgress(t *testing.T) {
	t.Parallel()
	store, _ := testStore(t, time.Hour)
	ctx := context.Background()
	tkn := tok(uuid.New(), "inflight")
	_ = mustClaim(t, ctx, claimCall{store: store, tkn: tkn, fp: "fp"})
	requireKind(t, mustClaim(t, ctx, claimCall{store: store, tkn: tkn, fp: "fp"}).Kind, KindInProgress)
}

func TestRedisStore_CrossOrgIsolation(t *testing.T) {
	t.Parallel()
	store, _ := testStore(t, time.Hour)
	ctx := context.Background()
	_ = mustClaim(t, ctx, claimCall{store: store, tkn: tok(uuid.New(), "shared-key"), fp: "fp"})
	requireKind(t, mustClaim(t, ctx, claimCall{store: store, tkn: tok(uuid.New(), "shared-key"), fp: "fp"}).Kind, KindMiss)
}

func TestRedisStore_ReleaseAllowsReclaim(t *testing.T) {
	t.Parallel()
	store, _ := testStore(t, time.Hour)
	ctx := context.Background()
	tkn := tok(uuid.New(), "rel")
	_ = mustClaim(t, ctx, claimCall{store: store, tkn: tkn, fp: "fp"})
	if err := store.Release(ctx, tkn, "fp"); err != nil {
		t.Fatalf("Release: %v", err)
	}
	requireKind(t, mustClaim(t, ctx, claimCall{store: store, tkn: tkn, fp: "fp"}).Kind, KindMiss)
}

func TestRedisStore_ConcurrentClaim(t *testing.T) {
	t.Parallel()
	store, _ := testStore(t, time.Hour)
	ctx := context.Background()
	tkn := tok(uuid.New(), "race")

	const n = 20
	kinds := concurrentClaimKinds(t, ctx, concurrentClaimParams{store: store, tkn: tkn, n: n})
	misses, inProg := countKinds(kinds)
	if misses != 1 {
		t.Fatalf("misses=%d want 1", misses)
	}
	if inProg != n-1 {
		t.Fatalf("in_progress=%d want %d", inProg, n-1)
	}
}

func concurrentClaimKinds(t *testing.T, ctx context.Context, p concurrentClaimParams) []Kind {
	t.Helper()
	kinds := make([]Kind, p.n)
	var wg sync.WaitGroup
	wg.Add(p.n)
	for i := 0; i < p.n; i++ {
		i := i
		go func() {
			defer wg.Done()
			out, err := p.store.Claim(ctx, p.tkn, "fp")
			if err != nil {
				t.Errorf("Claim: %v", err)
				return
			}
			kinds[i] = out.Kind
		}()
	}
	wg.Wait()
	return kinds
}

type concurrentClaimParams struct {
	store *RedisStore
	tkn   Token
	n     int
}

func countKinds(kinds []Kind) (misses, inProg int) {
	for _, k := range kinds {
		switch k {
		case KindMiss:
			misses++
		case KindInProgress:
			inProg++
		default:
			// Zero values from failed goroutines are ignored by the caller asserts.
		}
	}
	return misses, inProg
}

func TestRedisStore_ClaimCanceledContext(t *testing.T) {
	t.Parallel()
	store, _ := testStore(t, time.Hour)
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	_, err := store.Claim(ctx, tok(uuid.New(), "k"), "fp")
	if err == nil {
		t.Fatal("expected error on canceled ctx")
	}
}

func TestNoop_AlwaysMiss(t *testing.T) {
	t.Parallel()
	s := Noop()
	tkn := tok(uuid.New(), "k")
	out, err := s.Claim(context.Background(), tkn, "fp")
	if err != nil || out.Kind != KindMiss {
		t.Fatalf("Noop Claim: %+v %v", out, err)
	}
	if err := s.Commit(context.Background(), tkn, Record{}); err != nil {
		t.Fatalf("Noop Commit: %v", err)
	}
	if err := s.Release(context.Background(), tkn, "fp"); err != nil {
		t.Fatalf("Noop Release: %v", err)
	}
}

func TestRedisStore_PendingTTLExpiresThenReclaim(t *testing.T) {
	t.Parallel()
	store, mr := testStorePending(t, time.Hour, 50*time.Millisecond)
	ctx := context.Background()
	tkn := tok(uuid.New(), "orphan")
	_ = mustClaim(t, ctx, claimCall{store: store, tkn: tkn, fp: "fp"})
	mr.FastForward(100 * time.Millisecond)
	requireKind(t, mustClaim(t, ctx, claimCall{store: store, tkn: tkn, fp: "fp"}).Kind, KindMiss)
}

func TestRedisStore_CommitDoesNotClobberNewerOwner(t *testing.T) {
	t.Parallel()
	store, mr := testStorePending(t, time.Hour, 50*time.Millisecond)
	ctx := context.Background()
	tkn := tok(uuid.New(), "stale")

	_ = mustClaim(t, ctx, claimCall{store: store, tkn: tkn, fp: "fp-old"})
	mr.FastForward(100 * time.Millisecond)
	_ = mustClaim(t, ctx, claimCall{store: store, tkn: tkn, fp: "fp-new"})
	if err := store.Commit(ctx, tkn, Record{Fingerprint: "fp-new", Status: 200, Body: []byte(`new`)}); err != nil {
		t.Fatalf("Commit new: %v", err)
	}
	// Stale original claimant must not overwrite the newer completed record.
	if err := store.Commit(ctx, tkn, Record{Fingerprint: "fp-old", Status: 200, Body: []byte(`old`)}); err != nil {
		t.Fatalf("Commit old: %v", err)
	}
	out := mustClaim(t, ctx, claimCall{store: store, tkn: tkn, fp: "fp-new"})
	requireKind(t, out.Kind, KindHit)
	if string(out.Record.Body) != "new" {
		t.Fatalf("body=%q want new", out.Record.Body)
	}
}

func TestRedisStore_ReleaseWrongFingerprintNoOp(t *testing.T) {
	t.Parallel()
	store, mr := testStore(t, time.Hour)
	ctx := context.Background()
	tkn := tok(uuid.New(), "own")
	_ = mustClaim(t, ctx, claimCall{store: store, tkn: tkn, fp: "fp-a"})
	if err := store.Release(ctx, tkn, "fp-other"); err != nil {
		t.Fatalf("Release: %v", err)
	}
	if !mr.Exists(RedisKey(tkn)) {
		t.Fatal("expected key retained for wrong fingerprint release")
	}
}

func TestRedisStore_inspectExisting_reclaimAfterExpiry(t *testing.T) {
	t.Parallel()
	store, mr := testStorePending(t, time.Hour, time.Second)
	tkn := tok(uuid.New(), "race")
	redisKey := RedisKey(tkn)
	if err := mr.Set(redisKey, mustEncode(t, pendingRecord("fp"))); err != nil {
		t.Fatal(err)
	}
	mr.SetTTL(redisKey, time.Millisecond)
	mr.FastForward(10 * time.Millisecond)
	out, err := store.inspectExisting(context.Background(), pendingOwner{redisKey: redisKey, fingerprint: "fp"})
	if err != nil {
		t.Fatalf("inspectExisting: %v", err)
	}
	requireKind(t, out.Kind, KindMiss)
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
	tkn := tok(uuid.New(), "k")
	mr.Close()
	if _, err := store.Claim(context.Background(), tkn, "fp"); err == nil {
		t.Fatal("expected Claim error")
	}
	if err := store.Commit(context.Background(), tkn, Record{Fingerprint: "fp", Status: 200}); err == nil {
		t.Fatal("expected Commit error")
	}
	if err := store.Release(context.Background(), tkn, "fp"); err == nil {
		t.Fatal("expected Release error")
	}
}

func TestRedisStore_reclaimWhenKeyExists(t *testing.T) {
	t.Parallel()
	store, mr := testStore(t, time.Hour)
	tkn := tok(uuid.New(), "taken")
	redisKey := RedisKey(tkn)
	if err := mr.Set(redisKey, mustEncode(t, pendingRecord("fp"))); err != nil {
		t.Fatal(err)
	}
	out, err := store.reclaim(context.Background(), pendingOwner{redisKey: redisKey, fingerprint: "fp"})
	if err != nil {
		t.Fatal(err)
	}
	requireKind(t, out.Kind, KindInProgress)
	if out.Record.State != StatePending || out.Record.Fingerprint != "fp" {
		t.Fatalf("record=%+v want pending/fp", out.Record)
	}
}

func TestEncodeRecord_ZeroVersionDefaults(t *testing.T) {
	t.Parallel()
	raw := mustEncode(t, Record{State: StatePending, Fingerprint: "x"})
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
	_, err := store.reclaim(context.Background(), pendingOwner{redisKey: RedisKey(tok(uuid.New(), "k")), fingerprint: "fp"})
	if err == nil {
		t.Fatal("expected reclaim error")
	}
}

func TestRedisStore_inspectExistingGetError(t *testing.T) {
	t.Parallel()
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	store := NewRedisStore(client, Config{TTL: time.Hour})
	tkn := tok(uuid.New(), "geterr")
	if _, err := store.Claim(context.Background(), tkn, "fp"); err != nil {
		t.Fatal(err)
	}
	mr.Close()
	_, err := store.Claim(context.Background(), tkn, "fp")
	if err == nil {
		t.Fatal("expected Claim error on second attempt with redis down")
	}
}

func TestRedisStore_RejectUnsupportedVersion(t *testing.T) {
	t.Parallel()
	store, mr := testStore(t, time.Hour)
	tkn := tok(uuid.New(), "badver")
	if err := mr.Set(RedisKey(tkn), `{"v":99,"state":"completed","fp":"fp"}`); err != nil {
		t.Fatal(err)
	}
	_, err := store.Claim(context.Background(), tkn, "fp")
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
	got := RedisKey(tok(org, "abc"))
	want := "idempotency:550e8400-e29b-41d4-a716-446655440000:abc"
	if got != want {
		t.Fatalf("got %q want %q", got, want)
	}
}
