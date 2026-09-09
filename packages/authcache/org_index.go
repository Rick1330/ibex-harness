package authcache

import (
	"sync"
	"time"

	"github.com/google/uuid"
)

// orgIndex maps org UUID → set of digests for InvalidateByOrgID (ADR-0073)
// and retains bounded org-suspension tombstones so in-flight Validate cannot
// repopulate the LRU after an org suspend event.
type orgIndex struct {
	mu      sync.RWMutex
	byOrg   map[string]map[digest]struct{}
	tomb    map[string]time.Time // orgID → tombstone expiry
	tombTTL time.Duration
	now     func() time.Time
}

func newOrgIndex(tombTTL time.Duration, now func() time.Time) *orgIndex {
	if now == nil {
		now = time.Now
	}
	return &orgIndex{
		byOrg:   make(map[string]map[digest]struct{}),
		tomb:    make(map[string]time.Time),
		tombTTL: tombTTL,
		now:     now,
	}
}

func orgKey(orgID uuid.UUID) string {
	if orgID == uuid.Nil {
		return ""
	}
	return orgID.String()
}

func parseOrgKey(orgID string) (string, bool) {
	parsed, err := uuid.Parse(orgID)
	if err != nil {
		return "", false
	}
	key := orgKey(parsed)
	return key, key != ""
}

// put records orgID→hash unless a live tombstone rejects the insert.
func (idx *orgIndex) put(orgID uuid.UUID, hash digest) bool {
	key := orgKey(orgID)
	if key == "" {
		return true
	}
	idx.mu.Lock()
	defer idx.mu.Unlock()
	idx.pruneExpiredTombsLocked()
	if idx.tombLiveLocked(key) {
		return false
	}
	set, ok := idx.byOrg[key]
	if !ok {
		set = make(map[digest]struct{})
		idx.byOrg[key] = set
	}
	set[hash] = struct{}{}
	return true
}

// isSuspended reports whether orgID has a live suspension tombstone.
func (idx *orgIndex) isSuspended(orgID uuid.UUID) bool {
	key := orgKey(orgID)
	if key == "" {
		return false
	}
	idx.mu.RLock()
	defer idx.mu.RUnlock()
	until, ok := idx.tomb[key]
	return ok && idx.now().Before(until)
}

func (idx *orgIndex) removeDigest(orgID uuid.UUID, hash digest) {
	key := orgKey(orgID)
	if key == "" {
		return
	}
	idx.mu.Lock()
	defer idx.mu.Unlock()
	set, ok := idx.byOrg[key]
	if !ok {
		return
	}
	delete(set, hash)
	if len(set) == 0 {
		delete(idx.byOrg, key)
	}
}

// revoke installs an org tombstone and returns digests that must be evicted.
func (idx *orgIndex) revoke(orgID string) []digest {
	key, ok := parseOrgKey(orgID)
	if !ok {
		return nil
	}
	idx.mu.Lock()
	defer idx.mu.Unlock()
	idx.pruneExpiredTombsLocked()
	idx.tomb[key] = idx.now().Add(idx.tombTTL)
	set := idx.byOrg[key]
	delete(idx.byOrg, key)
	if len(set) == 0 {
		return nil
	}
	out := make([]digest, 0, len(set))
	for h := range set {
		out = append(out, h)
	}
	return out
}

func (idx *orgIndex) pruneExpiredTombsLocked() {
	now := idx.now()
	for orgID, until := range idx.tomb {
		if !now.Before(until) {
			delete(idx.tomb, orgID)
		}
	}
}

func (idx *orgIndex) tombLiveLocked(orgID string) bool {
	until, ok := idx.tomb[orgID]
	if !ok {
		return false
	}
	if idx.now().Before(until) {
		return true
	}
	delete(idx.tomb, orgID)
	return false
}
