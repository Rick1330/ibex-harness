package idempotency

import (
	"context"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
)

// BenchmarkIdempotency_Claim measures Claim miss cost against miniredis (MF-025).
// Run with: go test ./packages/idempotency/ -bench=BenchmarkIdempotency_Claim -benchmem
func BenchmarkIdempotency_Claim(b *testing.B) {
	mr := miniredis.RunT(b)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	b.Cleanup(func() { _ = client.Close() })
	store, err := NewRedisStore(client, Config{TTL: time.Hour, PendingTTL: time.Minute})
	if err != nil {
		b.Fatal(err)
	}
	org := uuid.MustParse("550e8400-e29b-41d4-a716-446655440088")
	ctx := context.Background()

	b.ReportAllocs()
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		tkn := Token{OrgID: org, Key: uuid.NewString()}
		if _, err := store.Claim(ctx, tkn, "bench-fp"); err != nil {
			b.Fatal(err)
		}
	}
}
