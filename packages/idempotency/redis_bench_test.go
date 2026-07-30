package idempotency

import (
	"context"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
)

// BenchmarkIdempotency_Claim measures first-claim (KindMiss) cost against miniredis (MF-025).
// Run with: go test ./packages/idempotency/ -bench=BenchmarkIdempotency_Claim -benchmem
func BenchmarkIdempotency_Claim(b *testing.B) {
	store, org, ctx := benchClaimSetup(b)
	keys := make([]string, b.N)
	for i := range keys {
		keys[i] = uuid.NewString()
	}

	b.ReportAllocs()
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		out, err := store.Claim(ctx, Token{OrgID: org, Key: keys[i]}, "bench-fp")
		if err != nil {
			b.Fatal(err)
		}
		if out.Kind != KindMiss {
			b.Fatalf("kind=%v want KindMiss", out.Kind)
		}
	}
}

// BenchmarkIdempotency_ClaimHit measures Claim replay (KindHit) against a committed key.
func BenchmarkIdempotency_ClaimHit(b *testing.B) {
	store, org, ctx := benchClaimSetup(b)
	tkn := Token{OrgID: org, Key: "bench-existing"}
	if _, err := store.Claim(ctx, tkn, "bench-fp"); err != nil {
		b.Fatal(err)
	}
	if err := store.Commit(ctx, tkn, Record{
		Version: CurrentRecordVersion, State: StateCompleted,
		Fingerprint: "bench-fp", Status: 200, Body: []byte(`{"ok":true}`),
	}); err != nil {
		b.Fatal(err)
	}

	b.ReportAllocs()
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		out, err := store.Claim(ctx, tkn, "bench-fp")
		if err != nil {
			b.Fatal(err)
		}
		if out.Kind != KindHit {
			b.Fatalf("kind=%v want KindHit", out.Kind)
		}
	}
}

func benchClaimSetup(b *testing.B) (*RedisStore, uuid.UUID, context.Context) {
	b.Helper()
	mr := miniredis.RunT(b)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	b.Cleanup(func() {
		if err := client.Close(); err != nil {
			b.Errorf("close Redis client: %v", err)
		}
	})
	store, err := NewRedisStore(client, Config{TTL: time.Hour, PendingTTL: time.Minute})
	if err != nil {
		b.Fatal(err)
	}
	org := uuid.MustParse("550e8400-e29b-41d4-a716-446655440088")
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	b.Cleanup(cancel)
	return store, org, ctx
}
