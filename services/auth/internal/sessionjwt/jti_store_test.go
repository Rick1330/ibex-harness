package sessionjwt_test

import (
	"context"
	"crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"encoding/pem"
	"errors"
	"strconv"
	"sync"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/services/auth/internal/sessionjwt"
	"github.com/alicebob/miniredis/v2"
	"github.com/redis/go-redis/v9"
)

type consumeResult struct {
	first bool
	err   error
}

func requireConsume(t *testing.T, got consumeResult, wantFirst bool, label string) {
	t.Helper()
	if got.err != nil {
		t.Fatalf("%s: %v", label, got.err)
	}
	if got.first != wantFirst {
		t.Fatalf("%s: first=%v want=%v", label, got.first, wantFirst)
	}
}

func TestMemoryJTIStore_HonorsTTL(t *testing.T) {
	t.Parallel()
	store := &sessionjwt.MemoryJTIStore{}
	ctx := context.Background()
	first, err := store.ConsumeOnce(ctx, "jti-ttl", 20*time.Millisecond)
	requireConsume(t, consumeResult{first, err}, true, "first")
	second, err := store.ConsumeOnce(ctx, "jti-ttl", time.Minute)
	requireConsume(t, consumeResult{second, err}, false, "replay before expiry")
	time.Sleep(30 * time.Millisecond)
	again, err := store.ConsumeOnce(ctx, "jti-ttl", time.Minute)
	requireConsume(t, consumeResult{again, err}, true, "after expiry")
}

func TestRedisJTIStore_NilClient(t *testing.T) {
	t.Parallel()
	if _, err := sessionjwt.NewRedisJTIStore(nil); err == nil {
		t.Fatal("expected nil client error")
	}
}

func TestRedisJTIStore_ConsumeOnce(t *testing.T) {
	t.Parallel()
	mr := miniredis.RunT(t)
	rdb := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = rdb.Close() })
	store, err := sessionjwt.NewRedisJTIStore(rdb)
	if err != nil {
		t.Fatal(err)
	}
	ctx := context.Background()
	first, err := store.ConsumeOnce(ctx, "jti-1", time.Minute)
	requireConsume(t, consumeResult{first, err}, true, "first")
	second, err := store.ConsumeOnce(ctx, "jti-1", time.Minute)
	requireConsume(t, consumeResult{second, err}, false, "replay")
	if err := store.RevokeSessionAndFamily(ctx, "sid-1", "family-1", time.Minute); err != nil {
		t.Fatal(err)
	}
	sessionRevoked, err := store.SessionRevoked(ctx, "sid-1")
	if err != nil || !sessionRevoked {
		t.Fatalf("session revocation marker: revoked=%v err=%v", sessionRevoked, err)
	}
	familyRevoked, err := store.FamilyRevoked(ctx, "family-1")
	if err != nil || !familyRevoked {
		t.Fatalf("family revocation marker: revoked=%v err=%v", familyRevoked, err)
	}
}

func TestRedisJTIStore_ZeroTTL(t *testing.T) {
	t.Parallel()
	mr := miniredis.RunT(t)
	rdb := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = rdb.Close() })
	store, err := sessionjwt.NewRedisJTIStore(rdb)
	if err != nil {
		t.Fatal(err)
	}
	ok, err := store.ConsumeOnce(context.Background(), "jti-2", 0)
	requireConsume(t, consumeResult{ok, err}, true, "zero ttl")
}

func TestIssuer_RefreshPair_UsesRedisJTIStore(t *testing.T) {
	t.Parallel()
	mr := miniredis.RunT(t)
	rdb := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = rdb.Close() })
	store, err := sessionjwt.NewRedisJTIStore(rdb)
	if err != nil {
		t.Fatal(err)
	}
	priv, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatal(err)
	}
	privPEM := string(pem.EncodeToMemory(&pem.Block{Type: "RSA PRIVATE KEY", Bytes: x509.MarshalPKCS1PrivateKey(priv)}))
	iss, err := sessionjwt.NewIssuer(sessionjwt.IssuerConfig{
		PrivateKeyPEM: sessionjwt.PrivateKeyPEM(privPEM), Issuer: sessionjwt.TokenIssuer("iss"), Audience: sessionjwt.TokenAudience("aud"),
		AccessTTL: time.Minute, RefreshTTL: time.Hour, StepUpTTL: time.Minute,
	})
	if err != nil {
		t.Fatal(err)
	}
	iss.WithJTIStore(store)
	_, refresh, _, _, err := iss.IssuePair(sessionjwt.IssuePairParams{Subject: "u", OrgID: "o", Permissions: 1})
	if err != nil {
		t.Fatal(err)
	}
	_, _, _, _, err = iss.RefreshPair(context.Background(), sessionjwt.RefreshToken(refresh))
	if err != nil {
		t.Fatal(err)
	}
	_, _, _, _, err = iss.RefreshPair(context.Background(), sessionjwt.RefreshToken(refresh))
	if !errors.Is(err, sessionjwt.ErrInvalidToken) {
		t.Fatalf("want replay err, got %v", err)
	}
}

func TestRefreshPair_ReuseRevokesFamilyDescendants(t *testing.T) {
	t.Parallel()
	iss := mustIssuer(t, time.Minute, time.Hour, time.Minute)
	_, r1, _, _, err := iss.IssuePair(sessionjwt.IssuePairParams{Subject: "u", OrgID: "o", Permissions: 1})
	if err != nil {
		t.Fatal(err)
	}
	_, r2, _, _, err := iss.RefreshPair(context.Background(), sessionjwt.RefreshToken(r1))
	if err != nil {
		t.Fatal(err)
	}
	_, _, _, _, err = iss.RefreshPair(context.Background(), sessionjwt.RefreshToken(r1))
	if !errors.Is(err, sessionjwt.ErrInvalidToken) {
		t.Fatalf("reuse: %v", err)
	}
	_, _, _, _, err = iss.RefreshPair(context.Background(), sessionjwt.RefreshToken(r2))
	if !errors.Is(err, sessionjwt.ErrInvalidToken) {
		t.Fatalf("descendant after family revoke: %v", err)
	}
}

func testIssuerWithStore(t *testing.T, redisBacked bool) *sessionjwt.Issuer {
	t.Helper()
	var store sessionjwt.JTIStore = &sessionjwt.MemoryJTIStore{}
	if redisBacked {
		mr := miniredis.RunT(t)
		rdb := redis.NewClient(&redis.Options{Addr: mr.Addr()})
		t.Cleanup(func() { _ = rdb.Close() })
		redisStore, err := sessionjwt.NewRedisJTIStore(rdb)
		if err != nil {
			t.Fatal(err)
		}
		store = redisStore
	}
	issuer := mustIssuer(t, time.Minute, time.Hour, time.Minute)
	issuer.WithJTIStore(store)
	return issuer
}

func concurrentStepUpWinners(t *testing.T, issuer *sessionjwt.Issuer) (int, int) {
	t.Helper()
	token, _, err := issuer.IssueStepUp(sessionjwt.IssueStepUpParams{
		Subject: "u", OrgID: "o", Permissions: 8, SessionID: "sid", Action: "legal_hold.manage",
	})
	if err != nil {
		t.Fatal(err)
	}
	expect := sessionjwt.StepUpExpectations{Subject: "u", OrgID: "o", SessionID: "sid", Action: "legal_hold.manage", RequiredPermission: 8}
	const workers = 32
	start := make(chan struct{})
	var wg sync.WaitGroup
	var mu sync.Mutex
	wins, unexpected := 0, 0
	for i := 0; i < workers; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			<-start
			_, consumeErr := issuer.ConsumeStepUp(context.Background(), sessionjwt.RawToken(token), expect)
			mu.Lock()
			defer mu.Unlock()
			if consumeErr == nil {
				wins++
			} else if !errors.Is(consumeErr, sessionjwt.ErrInvalidToken) {
				unexpected++
			}
		}()
	}
	close(start)
	wg.Wait()
	return wins, unexpected
}

func assertRefreshReplayRevokesAccess(t *testing.T, issuer *sessionjwt.Issuer) {
	t.Helper()
	access, refresh, _, _, err := issuer.IssuePair(sessionjwt.IssuePairParams{Subject: "u", OrgID: "o"})
	if err != nil {
		t.Fatal(err)
	}
	const workers = 16
	start := make(chan struct{})
	var wg sync.WaitGroup
	var mu sync.Mutex
	var descendants []string
	var unexpected error
	for i := 0; i < workers; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			<-start
			childAccess, _, _, _, refreshErr := issuer.RefreshPair(context.Background(), sessionjwt.RefreshToken(refresh))
			mu.Lock()
			defer mu.Unlock()
			if refreshErr == nil {
				descendants = append(descendants, childAccess)
			} else if !errors.Is(refreshErr, sessionjwt.ErrInvalidToken) {
				unexpected = refreshErr
			}
		}()
	}
	close(start)
	wg.Wait()
	if unexpected != nil {
		t.Fatalf("unexpected refresh error: %v", unexpected)
	}
	if len(descendants) == 0 {
		t.Fatal("expected one initial refresh to win")
	}
	for _, candidate := range append([]string{access}, descendants...) {
		if _, err := issuer.ValidateAccess(context.Background(), sessionjwt.RawToken(candidate)); !errors.Is(err, sessionjwt.ErrInvalidToken) {
			t.Fatalf("access token survived concurrent refresh replay: %v", err)
		}
	}
}

func TestIssuer_ConcurrentStepUpConsumptionHasExactlyOneWinner(t *testing.T) {
	for _, backend := range []struct {
		name        string
		redisBacked bool
	}{{name: "memory"}, {name: "redis", redisBacked: true}} {
		t.Run(backend.name, func(t *testing.T) {
			t.Parallel()
			issuer := testIssuerWithStore(t, backend.redisBacked)
			wins, unexpected := concurrentStepUpWinners(t, issuer)
			if wins != 1 || unexpected != 0 {
				t.Fatalf("step-up consumption: winners=%d unexpected=%d", wins, unexpected)
			}
		})
	}
}

func TestIssuer_ConcurrentRefreshReplayRevokesSessionAndReturnedAccess(t *testing.T) {
	for _, backend := range []struct {
		name        string
		redisBacked bool
	}{{name: "memory"}, {name: "redis", redisBacked: true}} {
		t.Run(backend.name, func(t *testing.T) {
			t.Parallel()
			assertRefreshReplayRevokesAccess(t, testIssuerWithStore(t, backend.redisBacked))
		})
	}
}

func BenchmarkMemoryJTIStore_ConsumeOnce(b *testing.B) {
	store := &sessionjwt.MemoryJTIStore{}
	ctx := context.Background()
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		jti := "bench-" + strconv.Itoa(i)
		_, _ = store.ConsumeOnce(ctx, jti, time.Minute)
	}
}
