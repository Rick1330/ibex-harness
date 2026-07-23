package authcache

import (
	"context"
	"errors"
	"fmt"
	"sync"
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

func testValidator(t *testing.T, up Validator, cfg Config, m Metrics) *CachingValidator {
	t.Helper()
	v, err := New(up, cfg, logger.Discard("authcache"), m)
	if err != nil {
		t.Fatalf("New: %v", err)
	}
	return v
}

func assertUpstreamCalls(t *testing.T, up *spyUpstream, want int64) {
	t.Helper()
	if got := up.calls.Load(); got != want {
		t.Fatalf("upstream calls=%d want %d", got, want)
	}
}

func TestUnit_TokenHashStable(t *testing.T) {
	t.Parallel()
	a := TokenHash("tok-abc")
	b := TokenHash("tok-abc")
	if a != b {
		t.Fatalf("hash not stable: %q vs %q", a, b)
	}
	if a == "tok-abc" || len(a) != 64 {
		t.Fatalf("hash=%q len=%d", a, len(a))
	}
}

func TestUnit_CachingValidatorLRUHit(t *testing.T) {
	t.Parallel()
	up := &spyUpstream{res: &Result{OrgID: "org-1", Permissions: 7}}
	m := &countingMetrics{}
	v := testValidator(t, up, Config{LRUMaxTTL: time.Minute}, m)

	r1, err := v.Validate(context.Background(), "token-1")
	if err != nil || r1.FromCache {
		t.Fatalf("first: err=%v fromCache=%v", err, r1 != nil && r1.FromCache)
	}
	r2, err := v.Validate(context.Background(), "token-1")
	if err != nil || !r2.FromCache {
		t.Fatalf("second: err=%v fromCache=%v", err, r2 != nil && r2.FromCache)
	}
	assertUpstreamCalls(t, up, 1)
	if m.hits.Load() != 1 {
		t.Fatalf("hits=%d want 1", m.hits.Load())
	}
}

func TestUnit_CachingValidatorRequiresSecondUpstream(t *testing.T) {
	t.Parallel()
	cases := []struct {
		name    string
		cfg     Config
		after   func(t *testing.T, v *CachingValidator, token string)
		advance time.Duration
	}{
		{
			name:    "ttl_expiry",
			cfg:     Config{LRUMaxTTL: 10 * time.Millisecond},
			advance: 20 * time.Millisecond,
		},
		{
			name: "invalidate",
			cfg:  Config{},
			after: func(t *testing.T, v *CachingValidator, token string) {
				t.Helper()
				v.Invalidate(TokenHash(token))
			},
		},
	}
	for _, tc := range cases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			up := &spyUpstream{res: &Result{OrgID: "org-1"}}
			v := testValidator(t, up, tc.cfg, NoopMetrics{})
			now := time.Now()
			v.now = func() time.Time { return now }
			token := "token-" + tc.name
			if _, err := v.Validate(context.Background(), token); err != nil {
				t.Fatalf("first: %v", err)
			}
			if tc.after != nil {
				tc.after(t, v, token)
			}
			if tc.advance > 0 {
				now = now.Add(tc.advance)
			}
			if _, err := v.Validate(context.Background(), token); err != nil {
				t.Fatalf("second: %v", err)
			}
			assertUpstreamCalls(t, up, 2)
		})
	}
}

func TestUnit_CachingValidatorBloomFalsePositive(t *testing.T) {
	t.Parallel()
	up := &spyUpstream{res: &Result{OrgID: "org-1"}}
	m := &countingMetrics{}
	v := testValidator(t, up, Config{}, m)
	token := "token-fp"
	v.bloom.add(hashToken(token))

	res, err := v.Validate(context.Background(), token)
	if err != nil || res.FromCache {
		t.Fatalf("err=%v fromCache=%v", err, res != nil && res.FromCache)
	}
	if m.bloomFP.Load() != 1 {
		t.Fatalf("bloomFP=%d want 1", m.bloomFP.Load())
	}
	assertUpstreamCalls(t, up, 1)
}

func TestUnit_CachingValidatorUpstreamDownFailsClosed(t *testing.T) {
	t.Parallel()
	up := &spyUpstream{err: ErrUnavailable}
	v := testValidator(t, up, Config{}, NoopMetrics{})
	_, err := v.Validate(context.Background(), "token-down")
	if !errors.Is(err, ErrUnavailable) {
		t.Fatalf("err=%v want ErrUnavailable", err)
	}
}

func TestUnit_CachingValidatorInvalidAddsBloom(t *testing.T) {
	t.Parallel()
	up := &spyUpstream{err: ErrInvalidToken}
	v := testValidator(t, up, Config{}, NoopMetrics{})
	token := "bad-token"
	_, err := v.Validate(context.Background(), token)
	if !errors.Is(err, ErrInvalidToken) {
		t.Fatalf("err=%v want ErrInvalidToken", err)
	}
	if !v.bloom.test(hashToken(token)) {
		t.Fatal("invalid token hash should be in bloom")
	}
}

func TestUnit_CachingValidatorBloomRotates(t *testing.T) {
	t.Parallel()
	up := &spyUpstream{err: ErrInvalidToken}
	v := testValidator(t, up, Config{BloomExpectedItems: 2}, NoopMetrics{})
	for i := 0; i < 3; i++ {
		_, err := v.Validate(context.Background(), fmt.Sprintf("bad-%d", i))
		if !errors.Is(err, ErrInvalidToken) {
			t.Fatalf("i=%d err=%v want ErrInvalidToken", i, err)
		}
	}
	v.bloom.mu.RLock()
	defer v.bloom.mu.RUnlock()
	if v.bloom.previous == nil {
		t.Fatal("expected previous generation after rotate")
	}
	if v.bloom.adds != 1 {
		t.Fatalf("adds after rotate=%d want 1", v.bloom.adds)
	}
}

func TestUnit_CachingValidatorConcurrentBloomAccess(t *testing.T) {
	t.Parallel()
	up := &dualUpstream{}
	v := testValidator(t, up, Config{BloomExpectedItems: 64}, NoopMetrics{})
	var wg sync.WaitGroup
	errCh := make(chan error, 64)
	for i := 0; i < 32; i++ {
		wg.Add(2)
		go func(i int) {
			defer wg.Done()
			res, err := v.Validate(context.Background(), fmt.Sprintf("ok-%d", i))
			if err != nil || res == nil || res.OrgID != "org-1" {
				errCh <- fmt.Errorf("ok-%d: res=%v err=%v", i, res, err)
			}
		}(i)
		go func(i int) {
			defer wg.Done()
			_, err := v.Validate(context.Background(), fmt.Sprintf("bad-%d", i))
			if !errors.Is(err, ErrInvalidToken) {
				errCh <- fmt.Errorf("bad-%d: err=%v want ErrInvalidToken", i, err)
			}
		}(i)
	}
	wg.Wait()
	close(errCh)
	for err := range errCh {
		t.Error(err)
	}
}

type dualUpstream struct {
	calls atomic.Int64
}

func (d *dualUpstream) Validate(_ context.Context, token string) (*Result, error) {
	d.calls.Add(1)
	if len(token) >= 4 && token[:4] == "bad-" {
		return nil, ErrInvalidToken
	}
	return &Result{OrgID: "org-1"}, nil
}

func TestUnit_CachingValidatorNilResultFailsClosed(t *testing.T) {
	t.Parallel()
	up := &spyUpstream{res: nil}
	v := testValidator(t, up, Config{}, NoopMetrics{})
	_, err := v.Validate(context.Background(), "nil-result")
	if !errors.Is(err, ErrUnavailable) {
		t.Fatalf("err=%v want ErrUnavailable", err)
	}
}

func TestUnit_CloneResultNil(t *testing.T) {
	t.Parallel()
	if cloneResult(nil, true) != nil {
		t.Fatal("expected nil")
	}
}

func TestUnit_ConfigValidateRejectsBadFPRate(t *testing.T) {
	t.Parallel()
	cfg := Config{
		LRUCapacity: 1, LRUMaxTTL: time.Second,
		BloomExpectedItems: 1, BloomFPRate: 0,
	}
	if err := cfg.Validate(); err == nil {
		t.Fatal("expected Validate error")
	}
}

func TestUnit_ConfigApplyDefaultsPreservesInvalid(t *testing.T) {
	t.Parallel()
	cfg := Config{LRUCapacity: -1, LRUMaxTTL: -time.Second, BloomFPRate: 1.5}
	cfg.ApplyDefaults()
	assertPreservedInvalidConfig(t, cfg)
	if err := cfg.Validate(); err == nil {
		t.Fatal("expected Validate error")
	}
}

func assertPreservedInvalidConfig(t *testing.T, cfg Config) {
	t.Helper()
	if cfg.LRUCapacity != -1 {
		t.Fatalf("LRUCapacity=%d", cfg.LRUCapacity)
	}
	if cfg.LRUMaxTTL != -time.Second {
		t.Fatalf("LRUMaxTTL=%s", cfg.LRUMaxTTL)
	}
	if cfg.BloomFPRate != 1.5 {
		t.Fatalf("BloomFPRate=%v", cfg.BloomFPRate)
	}
}

func TestUnit_NoopMetricsCallable(t *testing.T) {
	t.Parallel()
	var m Metrics = NoopMetrics{}
	m.IncAuthCacheHit("lru")
	m.IncAuthCacheMiss("bloom")
	m.SetAuthCacheLRUSize(1)
	m.IncAuthCacheLRUEviction()
	m.IncAuthCacheBloomFP()
}

func TestUnit_NewNilUpstream(t *testing.T) {
	t.Parallel()
	_, err := New(nil, Config{}, logger.Discard("authcache"), NoopMetrics{})
	if err == nil {
		t.Fatal("expected error")
	}
}

func TestUnit_CacheTTLSkipsNearExpiryToken(t *testing.T) {
	t.Parallel()
	up := &spyUpstream{res: &Result{
		OrgID:     "org-1",
		ExpiresAt: time.Now().Add(2 * time.Second),
	}}
	v := testValidator(t, up, Config{LRUMaxTTL: time.Minute}, NoopMetrics{})
	if _, err := v.Validate(context.Background(), "almost-expired"); err != nil {
		t.Fatalf("validate: %v", err)
	}
	assertUpstreamCalls(t, up, 1)
	if _, err := v.Validate(context.Background(), "almost-expired"); err != nil {
		t.Fatalf("second: %v", err)
	}
	assertUpstreamCalls(t, up, 2)
}

func TestUnit_MapUpstreamErrWrapsUnexpected(t *testing.T) {
	t.Parallel()
	boom := errors.New("boom")
	up := &spyUpstream{err: boom}
	v := testValidator(t, up, Config{}, NoopMetrics{})
	_, err := v.Validate(context.Background(), "tok")
	if !errors.Is(err, boom) {
		t.Fatalf("err=%v want wrapped boom", err)
	}
	if err.Error() == boom.Error() {
		t.Fatal("expected authcache validation context wrapping")
	}
}
