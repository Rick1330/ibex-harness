package authcache

import (
	"sync"
	"time"
)

// tokenIndex maps Result.TokenID → digest for InvalidateByTokenID (2.2.2 pub/sub)
// and retains bounded revocation tombstones so in-flight Validate cannot repopulate
// the LRU after a revoke.
type tokenIndex struct {
	mu      sync.RWMutex
	byID    map[string]digest
	tomb    map[string]time.Time // tokenID → tombstone expiry (now + LRUMaxTTL)
	tombTTL time.Duration
	now     func() time.Time
}

func newTokenIndex(tombTTL time.Duration, now func() time.Time) *tokenIndex {
	if now == nil {
		now = time.Now
	}
	return &tokenIndex{
		byID:    make(map[string]digest),
		tomb:    make(map[string]time.Time),
		tombTTL: tombTTL,
		now:     now,
	}
}

// put records tokenID→hash unless a live tombstone rejects the insert.
// Returns false when the put was rejected (caller must not cache).
func (idx *tokenIndex) put(tokenID string, hash digest) bool {
	if tokenID == "" {
		return true
	}
	idx.mu.Lock()
	defer idx.mu.Unlock()
	if idx.tombLiveLocked(tokenID) {
		return false
	}
	idx.byID[tokenID] = hash
	return true
}

// isRevoked reports whether tokenID has a live revocation tombstone.
func (idx *tokenIndex) isRevoked(tokenID string) bool {
	if tokenID == "" {
		return false
	}
	idx.mu.RLock()
	defer idx.mu.RUnlock()
	until, ok := idx.tomb[tokenID]
	return ok && idx.now().Before(until)
}

func (idx *tokenIndex) removeID(tokenID string) (digest, bool) {
	if tokenID == "" {
		return "", false
	}
	idx.mu.Lock()
	defer idx.mu.Unlock()
	hash, ok := idx.byID[tokenID]
	if ok {
		delete(idx.byID, tokenID)
	}
	return hash, ok
}

func (idx *tokenIndex) removeDigest(hash digest, tokenID string) {
	if tokenID == "" {
		return
	}
	idx.mu.Lock()
	defer idx.mu.Unlock()
	if cur, ok := idx.byID[tokenID]; ok && cur == hash {
		delete(idx.byID, tokenID)
	}
}

// markRevoked installs a tombstone for tokenID lasting tombTTL.
func (idx *tokenIndex) markRevoked(tokenID string) {
	if tokenID == "" {
		return
	}
	idx.mu.Lock()
	defer idx.mu.Unlock()
	idx.tomb[tokenID] = idx.now().Add(idx.tombTTL)
	delete(idx.byID, tokenID)
}

func (idx *tokenIndex) tombLiveLocked(tokenID string) bool {
	until, ok := idx.tomb[tokenID]
	if !ok {
		return false
	}
	if idx.now().Before(until) {
		return true
	}
	delete(idx.tomb, tokenID)
	return false
}
