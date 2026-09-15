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

func TestRedisJTIStore_ConsumeOnce(t *testing.T) {
	t.Parallel()
	mr := miniredis.RunT(t)
	rdb := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = rdb.Close() })
	store, err := sessionjwt.NewRedisJTIStore(rdb)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := sessionjwt.NewRedisJTIStore(nil); err == nil {
		t.Fatal("expected nil client error")
	}
	ctx := context.Background()
	first, err := store.ConsumeOnce(ctx, "jti-1", time.Minute)
	if err != nil || !first {
		t.Fatalf("first=%v err=%v", first, err)
	}
	second, err := store.ConsumeOnce(ctx, "jti-1", time.Minute)
	if err != nil || second {
		t.Fatalf("replay second=%v err=%v", second, err)
	}
	ok, err := store.ConsumeOnce(ctx, "jti-2", 0) // ttl clamped
	if err != nil || !ok {
		t.Fatalf("zero ttl: %v %v", ok, err)
	}
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
	privPEM := pem.EncodeToMemory(&pem.Block{Type: "RSA PRIVATE KEY", Bytes: x509.MarshalPKCS1PrivateKey(priv)})
	iss, err := sessionjwt.NewIssuer(string(privPEM), "iss", "aud", time.Minute, time.Hour, time.Minute)
	if err != nil {
		t.Fatal(err)
	}
	iss.WithJTIStore(store)
	_, refresh, _, _, err := iss.IssuePair("u", "o", 1)
	if err != nil {
		t.Fatal(err)
	}
	if _, _, _, _, err := iss.RefreshPair(context.Background(), refresh); err != nil {
		t.Fatal(err)
	}
	if _, _, _, _, err := iss.RefreshPair(context.Background(), refresh); !errors.Is(err, sessionjwt.ErrInvalidToken) {
		t.Fatalf("want replay err, got %v", err)
	}
}
