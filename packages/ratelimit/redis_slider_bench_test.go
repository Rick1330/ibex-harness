package ratelimit

import (
	"context"
	"testing"
	"time"

	"github.com/google/uuid"
)

// BenchmarkRedisSlider_Check measures the hot-path cost of a single org Check
// against miniredis (MF-025 partial). Run with:
//
//	go test ./packages/ratelimit/ -bench=BenchmarkRedisSlider_Check -benchmem
func BenchmarkRedisSlider_Check(b *testing.B) {
	// High RPM keeps the under-limit path for the full bench run.
	slider := newTestSlider(b, RedisSliderConfig{DefaultRPM: 1_000_000_000})
	orgID := uuid.MustParse("550e8400-e29b-41d4-a716-446655440099")
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	b.Cleanup(cancel)

	b.ReportAllocs()
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		if _, err := slider.Check(ctx, orgID, uuid.Nil); err != nil {
			b.Fatal(err)
		}
	}
}
