package authcache

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/google/uuid"
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
	tokenIdx *tokenIndex
	orgIdx   *orgIndex
	now      func() time.Time
	// afterTokenIndexPut is an optional test hook invoked after a successful
	// tokenIdx.put and before lru.Add (nil in production).
	afterTokenIndexPut func()
	// afterLRUClone is an optional test hook invoked after cloning an LRU hit
	// and before the second isRevoked check (nil in production).
	afterLRUClone func()
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
	now := time.Now
	v := &CachingValidator{
		upstream: upstream,
		cfg:      cfg,
		log:      log,
		metrics:  m,
		bloom:    newBloomFilter(cfg.BloomExpectedItems, cfg.BloomFPRate),
		tokenIdx: newTokenIndex(cfg.LRUMaxTTL, now),
		orgIdx:   newOrgIndex(cfg.LRUMaxTTL, now),
		now:      now,
	}
	cache, err := lru.NewWithEvict[digest, *cachedEntry](cfg.LRUCapacity, func(hash digest, entry *cachedEntry) {
		m.IncAuthCacheLRUEviction()
		if entry != nil {
			v.tokenIdx.removeDigest(hash, entry.result.TokenID)
			v.orgIdx.removeDigest(entry.result.OrgID, hash)
		}
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

// Invalidate removes a token hash from the LRU synchronously.
func (v *CachingValidator) Invalidate(tokenHash string) {
	if tokenHash == "" {
		return
	}
	v.dropCachedHash(digestFromHex(tokenHash))
	v.metrics.SetAuthCacheLRUSize(float64(v.lru.Len()))
}

// InvalidateByTokenID removes a cached claims entry by token UUID (2.2.2 pub/sub)
// and installs a bounded tombstone so in-flight upstream results cannot repopulate.
func (v *CachingValidator) InvalidateByTokenID(tokenID string) {
	hash, ok := v.tokenIdx.revoke(tokenID)
	if !ok {
		return
	}
	v.invalidateAfterRevoke([]digest{hash})
}

// InvalidateByOrgID removes all cached claims for an organization (ADR-0073
// org_suspend) and installs a bounded tombstone so in-flight upstream results
// cannot repopulate until the next authoritative ValidateToken.
func (v *CachingValidator) InvalidateByOrgID(orgID string) {
	v.invalidateAfterRevoke(v.orgIdx.revoke(orgID))
}

func (v *CachingValidator) invalidateAfterRevoke(hashes []digest) {
	for _, hash := range hashes {
		v.dropCachedHash(hash)
	}
	v.metrics.SetAuthCacheLRUSize(float64(v.lru.Len()))
}

func (v *CachingValidator) dropCachedHash(hash digest) {
	if entry, ok := v.lru.Get(hash); ok && entry != nil {
		v.tokenIdx.removeDigest(hash, entry.result.TokenID)
		v.orgIdx.removeDigest(entry.result.OrgID, hash)
	}
	v.lru.Remove(hash)
}

func (v *CachingValidator) cacheBlocked(tokenID string, orgID uuid.UUID) bool {
	return v.tokenIdx.isRevoked(tokenID) || v.orgIdx.isSuspended(orgID)
}

func (v *CachingValidator) lookupLRU(hash digest) (*Result, bool) {
	entry, ok := v.lru.Get(hash)
	if !ok || entry == nil {
		return nil, false
	}
	if !v.now().Before(entry.expiresAt) || v.cacheBlocked(entry.result.TokenID, entry.result.OrgID) {
		v.evictRevoked(hash, entry.result.TokenID, entry.result.OrgID)
		return nil, false
	}
	// Re-check after clone: InvalidateByTokenID/OrgID may race between check and return.
	out := cloneResult(&entry.result, true)
	if v.afterLRUClone != nil {
		v.afterLRUClone()
	}
	if v.cacheBlocked(entry.result.TokenID, entry.result.OrgID) {
		v.evictRevoked(hash, entry.result.TokenID, entry.result.OrgID)
		return nil, false
	}
	return out, true
}

func (v *CachingValidator) evictRevoked(hash digest, tokenID string, orgID uuid.UUID) {
	v.tokenIdx.removeDigest(hash, tokenID)
	v.orgIdx.removeDigest(orgID, hash)
	v.lru.Remove(hash)
	v.metrics.SetAuthCacheLRUSize(float64(v.lru.Len()))
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
	if errors.Is(err, ErrOrgSuspended) {
		// Do not bloom: org may be reactivated; fail closed without poisoning.
		return ErrOrgSuspended
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
	if !v.tokenIdx.put(res.TokenID, hash) {
		return
	}
	if !v.orgIdx.put(res.OrgID, hash) {
		v.tokenIdx.removeDigest(hash, res.TokenID)
		return
	}
	if v.afterTokenIndexPut != nil {
		v.afterTokenIndexPut()
	}
	entry := &cachedEntry{
		result:    *cloneResult(res, false),
		expiresAt: v.now().Add(ttl),
	}
	v.lru.Add(hash, entry)
	// Concurrent InvalidateByTokenID/OrgID may have run between put and Add.
	if v.cacheBlocked(res.TokenID, res.OrgID) {
		v.evictRevoked(hash, res.TokenID, res.OrgID)
	}
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
