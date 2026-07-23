package authcache

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	lru "github.com/hashicorp/golang-lru/v2"
)

type cachedEntry struct {
	result    Result
	expiresAt time.Time
}

// CachingValidator is a two-tier invalid-token bloom + claims LRU in front of Validator.
type CachingValidator struct {
	upstream Validator
	cfg      Config
	log      *logger.Logger
	metrics  Metrics
	bloom    *bloomFilter
	lru      *lru.Cache[digest, *cachedEntry]
	now      func() time.Time
}

// New constructs a CachingValidator. cfg defaults are applied before validate.
func New(upstream Validator, cfg Config, log *logger.Logger, m Metrics) (*CachingValidator, error) {
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
		bloom:    newBloomFilter(cfg.BloomExpectedItems, cfg.BloomFPRate),
		now:      time.Now,
	}
	cache, err := lru.NewWithEvict[digest, *cachedEntry](cfg.LRUCapacity, func(digest, *cachedEntry) {
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
	call := upstreamCall{token: token, hash: hashToken(token)}
	if v.bloom.test(call.hash) {
		call.bloomSaidInvalid = true
		return v.fetchUpstream(ctx, call)
	}
	if res, ok := v.lookupLRU(call.hash); ok {
		v.metrics.IncAuthCacheHit("lru")
		return res, nil
	}
	v.metrics.IncAuthCacheMiss("lru")
	return v.fetchUpstream(ctx, call)
}

// Invalidate removes a token hash from the LRU synchronously (2.2.2 pub/sub).
func (v *CachingValidator) Invalidate(tokenHash string) {
	if tokenHash == "" {
		return
	}
	v.lru.Remove(digestFromHex(tokenHash))
	v.metrics.SetAuthCacheLRUSize(float64(v.lru.Len()))
}

func (v *CachingValidator) lookupLRU(hash digest) (*Result, bool) {
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

type upstreamCall struct {
	token            string
	hash             digest
	bloomSaidInvalid bool
}

func (v *CachingValidator) fetchUpstream(ctx context.Context, call upstreamCall) (*Result, error) {
	if call.bloomSaidInvalid {
		v.metrics.IncAuthCacheMiss("bloom")
	}
	res, err := v.upstream.Validate(ctx, call.token)
	if err != nil {
		return nil, v.mapUpstreamErr(call.hash, err)
	}
	if res == nil {
		return nil, ErrUnavailable
	}
	if call.bloomSaidInvalid {
		v.metrics.IncAuthCacheBloomFP()
	}
	v.putLRU(call.hash, res)
	return cloneResult(res, false), nil
}

func (v *CachingValidator) mapUpstreamErr(hash digest, err error) error {
	if errors.Is(err, ErrInvalidToken) {
		v.bloom.add(hash)
		return ErrInvalidToken
	}
	if errors.Is(err, ErrUnavailable) {
		return ErrUnavailable
	}
	return fmt.Errorf("authcache: upstream validate: %w", err)
}

func (v *CachingValidator) putLRU(hash digest, res *Result) {
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
