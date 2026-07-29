package authcache

import (
	"context"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/google/uuid"
)

func BenchmarkCachingValidator_LRUHit(b *testing.B) {
	up := &spyUpstream{res: &Result{
		OrgID:       uuid.MustParse("11111111-1111-4111-8111-111111111111"),
		Permissions: 1,
	}}
	v, err := New(up, Config{}, logger.Discard("authcache"), NoopMetrics{})
	if err != nil {
		b.Fatalf("New: %v", err)
	}
	ctx := context.Background()
	token := "bench-token"
	if _, err := v.Validate(ctx, token); err != nil {
		b.Fatalf("warm: %v", err)
	}
	b.ReportAllocs()
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		if _, err := v.Validate(ctx, token); err != nil {
			b.Fatal(err)
		}
	}
}
