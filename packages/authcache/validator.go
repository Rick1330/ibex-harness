package authcache

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/bits-and-blooms/bloom/v3"
	lru "github.com/hashicorp/golang-lru/v2"
)

type cachedEntry struct {
	result    Result
	expiresAt time.Time
}

// CachingValidator is a two-tier invalid-token bloom + claims LRU in front of Upstream.
type CachingValidator struct {
	upstream Upstream
	cfg      Config
	log      *logger.Logger
	metrics  Metrics
	bloom    *bloom.BloomFilter
	lru      *lru.Cache[string, *cachedEntry]
	now      func() time.Time
}

// New constructs a CachingValidator. cfg defaults are applied before validate.
func New(upstream Upstream, cfg Config, log *logger.Logger, m Metrics) (*CachingValidator, error) {
	if upstream == nil {
		return nil, errors.New("authcache: upstream is required")
	}
	if log == nil {
		return nil, errors.New("authcache: logger is required")
	}
	if m == nil {
		m = NoopMetrics{}
	}
	cfg.ApplyDefaults()
	if err := cfg.Validate(); err != nil {
		return nil, err
	}
	v := &CachingValidator{
		upstream: upstream,
		cfg:      cfg,
		log:      log,
		metrics:  m,
		bloom:    bloom.NewWithEstimates(cfg.BloomExpectedItems, cfg.BloomFPRate),
		now:      time.Now,
	}
	cache, err := lru.NewWithEvict[string, *cachedEntry](cfg.LRUCapacity, func(string, *cachedEntry) {
		m.IncAuthCacheLRUEviction()
	})
	if err != nil {
		return nil, fmt.Errorf("authcache: lru: %w", err)
	}
	v.lru = cache
	return v, nil
}

// Validate resolves claims via bloom → LRU → upstream (fail closed on upstream error).
func (v *CachingValidator) Validate(ctx context.Context, token string) (*Result, error) {
	hash := TokenHash(token)
	if v.bloom.TestString(hash) {
		return v.validateViaUpstream(ctx, token, hash, true)
	}
	if res, ok := v.lookupLRU(hash); ok {
		v.metrics.IncAuthCacheHit("lru")
		return res, nil
	}
	v.metrics.IncAuthCacheMiss("lru")
	return v.validateViaUpstream(ctx, token, hash, false)
}

// Invalidate removes a token hash from the LRU synchronously (2.2.2 pub/sub).
func (v *CachingValidator) Invalidate(tokenHash string) {
	if tokenHash == "" {
		return
	}
	v.lru.Remove(tokenHash)
	v.metrics.SetAuthCacheLRUSize(float64(v.lru.Len()))
}

func (v *CachingValidator) lookupLRU(hash string) (*Result, bool) {
	entry, ok := v.lru.Get(hash)
	if !ok || entry == nil {
		return nil, false
	}
	if !v.now().Before(entry.expiresAt) {
		v.lru.Remove(hash)
		v.metrics.SetAuthCacheLRUSize(float64(v.lru.Len()))
		return nil, false
	}
	return cloneResult(&entry.result, true), true
}

func (v *CachingValidator) validateViaUpstream(
	ctx context.Context, token, hash string, bloomSaidInvalid bool,
) (*Result, error) {
	if bloomSaidInvalid {
		v.metrics.IncAuthCacheMiss("bloom")
	}
	res, err := v.upstream.Validate(ctx, token)
	if err != nil {
		return nil, v.handleUpstreamError(hash, err)
	}
	if bloomSaidInvalid {
		v.metrics.IncAuthCacheBloomFP()
	}
	v.putLRU(hash, res)
	return cloneResult(res, false), nil
}

func (v *CachingValidator) handleUpstreamError(hash string, err error) error {
	if errors.Is(err, ErrInvalidToken) {
		v.bloom.AddString(hash)
		return ErrInvalidToken
	}
	if errors.Is(err, ErrUnavailable) {
		return ErrUnavailable
	}
	return err
}

func (v *CachingValidator) putLRU(hash string, res *Result) {
	ttl := v.cacheTTL(res)
	if ttl <= 0 {
		return
	}
	entry := &cachedEntry{
		result:    *cloneResult(res, false),
		expiresAt: v.now().Add(ttl),
	}
	v.lru.Add(hash, entry)
	v.metrics.SetAuthCacheLRUSize(float64(v.lru.Len()))
}

func (v *CachingValidator) cacheTTL(res *Result) time.Duration {
	ttl := v.cfg.LRUMaxTTL
	if res == nil || res.ExpiresAt.IsZero() {
		return ttl
	}
	until := res.ExpiresAt.Sub(v.now()) - tokenExpirySkew
	if until < ttl {
		return until
	}
	return ttl
}
