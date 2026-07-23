package authcache

import "sync"

// byTokenID maps Result.TokenID → digest for InvalidateByTokenID (2.2.2 pub/sub).
// Protected separately from the LRU (which is already concurrent-safe).
type tokenIndex struct {
	mu   sync.RWMutex
	byID map[string]digest
}

func newTokenIndex() *tokenIndex {
	return &tokenIndex{byID: make(map[string]digest)}
}

func (idx *tokenIndex) put(tokenID string, hash digest) {
	if tokenID == "" {
		return
	}
	idx.mu.Lock()
	idx.byID[tokenID] = hash
	idx.mu.Unlock()
}

func (idx *tokenIndex) removeID(tokenID string) (digest, bool) {
	if tokenID == "" {
		return "", false
	}
	idx.mu.Lock()
	defer idx.mu.Unlock()
	hash, ok := idx.byID[tokenID]
	if !ok {
		return "", false
	}
	delete(idx.byID, tokenID)
	return hash, true
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
