package sessionjwt_test

import (
	"context"
	"crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"encoding/pem"
	"errors"
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
		PrivateKeyPEM: privPEM, Issuer: "iss", Audience: "aud",
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
	_, _, _, _, err = iss.RefreshPair(context.Background(), refresh)
	if err != nil {
		t.Fatal(err)
	}
	_, _, _, _, err = iss.RefreshPair(context.Background(), refresh)
	if !errors.Is(err, sessionjwt.ErrInvalidToken) {
		t.Fatalf("want replay err, got %v", err)
	}
}
