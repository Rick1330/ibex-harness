package authcache

import (
	"context"
	"errors"
	"fmt"
	"strings"
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
			if err := assertConcurrentOK(v, i); err != nil {
				errCh <- err
			}
		}(i)
		go func(i int) {
			defer wg.Done()
			if err := assertConcurrentInvalid(v, i); err != nil {
				errCh <- err
			}
		}(i)
	}
	wg.Wait()
	close(errCh)
	for err := range errCh {
		t.Error(err)
	}
}

func assertConcurrentOK(v *CachingValidator, i int) error {
	res, err := v.Validate(context.Background(), fmt.Sprintf("ok-%d", i))
	if err != nil {
		return fmt.Errorf("ok-%d: %w", i, err)
	}
	if res == nil {
		return fmt.Errorf("ok-%d: nil result", i)
	}
	if res.OrgID != "org-1" {
		return fmt.Errorf("ok-%d: org=%q", i, res.OrgID)
	}
	return nil
}

func assertConcurrentInvalid(v *CachingValidator, i int) error {
	_, err := v.Validate(context.Background(), fmt.Sprintf("bad-%d", i))
	if errors.Is(err, ErrInvalidToken) {
		return nil
	}
	return fmt.Errorf("bad-%d: err=%v want ErrInvalidToken", i, err)
}

type dualUpstream struct {
	calls atomic.Int64
}

func (d *dualUpstream) Validate(_ context.Context, token string) (*Result, error) {
	d.calls.Add(1)
	if strings.HasPrefix(token, "bad-") {
		return nil, ErrInvalidToken
	}
	return &Result{OrgID: "org-1"}, nil
}

func TestUnit_CachingValidatorInvalidateByTokenID(t *testing.T) {
	t.Parallel()
	up := &spyUpstream{res: &Result{OrgID: "org-1", TokenID: "tok-uuid-1"}}
	v := testValidator(t, up, Config{}, NoopMetrics{})
	if _, err := v.Validate(context.Background(), "bearer-1"); err != nil {
		t.Fatalf("first: %v", err)
	}
	assertUpstreamCalls(t, up, 1)
	v.InvalidateByTokenID("tok-uuid-1")
	res, err := v.Validate(context.Background(), "bearer-1")
	if err != nil {
		t.Fatalf("second: %v", err)
	}
	if res.FromCache {
		t.Fatal("expected miss after InvalidateByTokenID")
	}
	assertUpstreamCalls(t, up, 2)
}

func TestUnit_CachingValidatorRevokeBetweenLRUCloneAndReturn(t *testing.T) {
	t.Parallel()
	up := &spyUpstream{res: &Result{OrgID: "org-1", TokenID: "tok-clone"}}
	v := testValidator(t, up, Config{LRUMaxTTL: time.Minute}, NoopMetrics{})
	if _, err := v.Validate(context.Background(), "bearer-clone"); err != nil {
		t.Fatalf("seed: %v", err)
	}
	assertUpstreamCalls(t, up, 1)

	v.afterLRUClone = func() {
		v.InvalidateByTokenID("tok-clone")
	}
	res, err := v.Validate(context.Background(), "bearer-clone")
	if err != nil {
		t.Fatalf("validate: %v", err)
	}
	if res.FromCache {
		t.Fatal("revoked during LRU clone must not serve cached claims")
	}
	assertUpstreamCalls(t, up, 2)
}

func TestUnit_CachingValidatorInvalidateByTokenIDEmptyNoop(t *testing.T) {
	t.Parallel()
	up := &spyUpstream{res: &Result{OrgID: "org-1", TokenID: "tok-2"}}
	v := testValidator(t, up, Config{}, NoopMetrics{})
	if _, err := v.Validate(context.Background(), "bearer-2"); err != nil {
		t.Fatalf("validate: %v", err)
	}
	v.InvalidateByTokenID("")
	v.InvalidateByTokenID("missing")
	res, err := v.Validate(context.Background(), "bearer-2")
	if err != nil || !res.FromCache {
		t.Fatalf("expected cache hit err=%v fromCache=%v", err, res != nil && res.FromCache)
	}
	assertUpstreamCalls(t, up, 1)
}

func TestUnit_CachingValidatorConcurrentInvalidateByTokenID(t *testing.T) {
	t.Parallel()
	up := &spyUpstream{res: &Result{OrgID: "org-1", TokenID: "tok-conc"}}
	v := testValidator(t, up, Config{LRUCapacity: 64}, NoopMetrics{})
	if _, err := v.Validate(context.Background(), "bearer-conc"); err != nil {
		t.Fatalf("seed: %v", err)
	}
	var wg sync.WaitGroup
	for i := 0; i < 32; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			v.InvalidateByTokenID("tok-conc")
		}()
	}
	wg.Wait()
	res, err := v.Validate(context.Background(), "bearer-conc")
	if err != nil {
		t.Fatalf("after: %v", err)
	}
	if res.FromCache {
		t.Fatal("expected miss after concurrent invalidate")
	}
}

type blockingUpstream struct {
	release chan struct{}
	started chan struct{}
	res     *Result
	calls   atomic.Int64
}

func (b *blockingUpstream) Validate(context.Context, string) (*Result, error) {
	b.calls.Add(1)
	select {
	case b.started <- struct{}{}:
	default:
	}
	<-b.release
	return cloneResult(b.res, false), nil
}

func TestUnit_CachingValidatorTombstoneBlocksStalePut(t *testing.T) {
	t.Parallel()
	up := &blockingUpstream{
		release: make(chan struct{}),
		started: make(chan struct{}, 1),
		res:     &Result{OrgID: "org-1", TokenID: "tok-race"},
	}
	v := testValidator(t, up, Config{LRUMaxTTL: time.Minute}, NoopMetrics{})

	errCh := make(chan error, 1)
	go func() {
		_, err := v.Validate(context.Background(), "bearer-race")
		errCh <- err
	}()
	select {
	case <-up.started:
	case <-time.After(time.Second):
		t.Fatal("upstream did not start")
	}
	v.InvalidateByTokenID("tok-race")
	close(up.release)
	if err := <-errCh; err != nil {
		t.Fatalf("in-flight validate: %v", err)
	}

	res, err := v.Validate(context.Background(), "bearer-race")
	if err != nil {
		t.Fatalf("second validate: %v", err)
	}
	if res.FromCache {
		t.Fatal("stale in-flight result must not populate cache after revoke")
	}
	if up.calls.Load() < 2 {
		t.Fatalf("upstream calls=%d want >= 2", up.calls.Load())
	}
}

func TestUnit_CachingValidatorRevokeBetweenPutAndAdd(t *testing.T) {
	t.Parallel()
	up := &spyUpstream{res: &Result{OrgID: "org-1", TokenID: "tok-gap"}}
	v := testValidator(t, up, Config{LRUMaxTTL: time.Minute}, NoopMetrics{})

	indexed := make(chan struct{})
	resume := make(chan struct{})
	v.afterTokenIndexPut = func() {
		close(indexed)
		<-resume
	}

	errCh := make(chan error, 1)
	go func() {
		_, err := v.Validate(context.Background(), "bearer-gap")
		errCh <- err
	}()
	select {
	case <-indexed:
	case <-time.After(time.Second):
		t.Fatal("index put did not run")
	}
	v.InvalidateByTokenID("tok-gap")
	close(resume)
	if err := <-errCh; err != nil {
		t.Fatalf("validate: %v", err)
	}

	res, err := v.Validate(context.Background(), "bearer-gap")
	if err != nil {
		t.Fatalf("second: %v", err)
	}
	if res.FromCache {
		t.Fatal("stale LRU add after revoke must not serve from cache")
	}
	assertUpstreamCalls(t, up, 2)
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
