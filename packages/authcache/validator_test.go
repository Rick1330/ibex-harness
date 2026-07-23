package authcache

import (
	"context"
	"errors"
	"sync/atomic"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
)

type spyUpstream struct {
	calls atomic.Int64
	res   *Result
	err   error
}

func (s *spyUpstream) Validate(context.Context, string) (*Result, error) {
	s.calls.Add(1)
	if s.err != nil {
		return nil, s.err
	}
	return cloneResult(s.res, false), nil
}

type countingMetrics struct {
	hits, misses, bloomFP, evictions atomic.Int64
	lruSize                          atomic.Int64
}

func (m *countingMetrics) IncAuthCacheHit(string)  { m.hits.Add(1) }
func (m *countingMetrics) IncAuthCacheMiss(string) { m.misses.Add(1) }
func (m *countingMetrics) SetAuthCacheLRUSize(n float64) {
	m.lruSize.Store(int64(n))
}
func (m *countingMetrics) IncAuthCacheLRUEviction() { m.evictions.Add(1) }
func (m *countingMetrics) IncAuthCacheBloomFP()     { m.bloomFP.Add(1) }

func testValidator(t *testing.T, up Upstream, cfg Config, m Metrics) *CachingValidator {
	t.Helper()
	v, err := New(up, cfg, logger.Discard("authcache"), m)
	if err != nil {
		t.Fatalf("New: %v", err)
	}
	return v
}

func TestTokenHash_stable(t *testing.T) {
	a := TokenHash("tok-abc")
	b := TokenHash("tok-abc")
	if a != b {
		t.Fatalf("hash not stable: %q vs %q", a, b)
	}
	if a == "tok-abc" {
		t.Fatal("hash must not equal raw token")
	}
	if len(a) != 64 {
		t.Fatalf("expected sha256 hex length 64, got %d", len(a))
	}
}

func TestCachingValidator_LRUHit(t *testing.T) {
	up := &spyUpstream{res: &Result{OrgID: "org-1", Permissions: 7}}
	m := &countingMetrics{}
	v := testValidator(t, up, Config{LRUMaxTTL: time.Minute}, m)

	r1, err := v.Validate(context.Background(), "token-1")
	if err != nil {
		t.Fatalf("first validate: %v", err)
	}
	if r1.FromCache {
		t.Fatal("first result should not be from cache")
	}
	r2, err := v.Validate(context.Background(), "token-1")
	if err != nil {
		t.Fatalf("second validate: %v", err)
	}
	if !r2.FromCache {
		t.Fatal("second result should be from cache")
	}
	if up.calls.Load() != 1 {
		t.Fatalf("upstream calls=%d want 1", up.calls.Load())
	}
	if m.hits.Load() != 1 {
		t.Fatalf("hits=%d want 1", m.hits.Load())
	}
}

func TestCachingValidator_LRUTTLExpiry(t *testing.T) {
	up := &spyUpstream{res: &Result{OrgID: "org-1"}}
	v := testValidator(t, up, Config{LRUMaxTTL: 10 * time.Millisecond}, NoopMetrics{})
	now := time.Now()
	v.now = func() time.Time { return now }

	if _, err := v.Validate(context.Background(), "token-ttl"); err != nil {
		t.Fatalf("first: %v", err)
	}
	now = now.Add(20 * time.Millisecond)
	if _, err := v.Validate(context.Background(), "token-ttl"); err != nil {
		t.Fatalf("after expiry: %v", err)
	}
	if up.calls.Load() != 2 {
		t.Fatalf("upstream calls=%d want 2", up.calls.Load())
	}
}

func TestCachingValidator_Invalidate(t *testing.T) {
	up := &spyUpstream{res: &Result{OrgID: "org-1"}}
	v := testValidator(t, up, Config{}, NoopMetrics{})
	token := "token-inv"
	if _, err := v.Validate(context.Background(), token); err != nil {
		t.Fatalf("first: %v", err)
	}
	v.Invalidate(TokenHash(token))
	if _, err := v.Validate(context.Background(), token); err != nil {
		t.Fatalf("after invalidate: %v", err)
	}
	if up.calls.Load() != 2 {
		t.Fatalf("upstream calls=%d want 2", up.calls.Load())
	}
}

func TestCachingValidator_BloomFalsePositive(t *testing.T) {
	up := &spyUpstream{res: &Result{OrgID: "org-1"}}
	m := &countingMetrics{}
	v := testValidator(t, up, Config{}, m)
	token := "token-fp"
	hash := TokenHash(token)
	v.bloom.AddString(hash)

	res, err := v.Validate(context.Background(), token)
	if err != nil {
		t.Fatalf("validate: %v", err)
	}
	if res.FromCache {
		t.Fatal("bloom path should not mark FromCache")
	}
	if m.bloomFP.Load() != 1 {
		t.Fatalf("bloomFP=%d want 1", m.bloomFP.Load())
	}
	if up.calls.Load() != 1 {
		t.Fatalf("upstream calls=%d want 1", up.calls.Load())
	}
}

func TestCachingValidator_UpstreamDown_FailsClosed(t *testing.T) {
	up := &spyUpstream{err: ErrUnavailable}
	v := testValidator(t, up, Config{}, NoopMetrics{})
	_, err := v.Validate(context.Background(), "token-down")
	if !errors.Is(err, ErrUnavailable) {
		t.Fatalf("err=%v want ErrUnavailable", err)
	}
}

func TestCachingValidator_InvalidAddsBloom(t *testing.T) {
	up := &spyUpstream{err: ErrInvalidToken}
	v := testValidator(t, up, Config{}, NoopMetrics{})
	token := "bad-token"
	_, err := v.Validate(context.Background(), token)
	if !errors.Is(err, ErrInvalidToken) {
		t.Fatalf("err=%v want ErrInvalidToken", err)
	}
	if !v.bloom.TestString(TokenHash(token)) {
		t.Fatal("invalid token hash should be in bloom")
	}
}
