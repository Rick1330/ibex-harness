package sessionjwt

import (
	"context"
	"fmt"
	"sync"
	"sync/atomic"
	"time"

	"github.com/redis/go-redis/v9"
)

const (
	refreshJTIKeyPrefix           = "auth:session:refresh-jti:"
	refreshFamilyRevokedKeyPrefix = "auth:session:refresh-family-revoked:"
	sessionRevokedKeyPrefix       = "auth:session:revoked:"
	accessRevokedKeyPrefix        = "auth:session:access-revoked:"
	stepUpJTIKeyPrefix            = "auth:session:step-up-jti:"
	memoryJTIPurgeEveryN          = 64
	memoryJTIPurgeMinInterval     = time.Minute
)

// JTIStore atomically tracks consumed refresh JTIs and revoked refresh families.
type JTIStore interface {
	// ConsumeOnce returns true when jti was recorded for the first time.
	ConsumeOnce(ctx context.Context, jti string, ttl time.Duration) (bool, error)
	// RevokeFamily marks a refresh-token family revoked (reuse detection).
	RevokeFamily(ctx context.Context, familyID string, ttl time.Duration) error
	// FamilyRevoked reports whether the family was revoked.
	FamilyRevoked(ctx context.Context, familyID string) (bool, error)
	RevokeSession(ctx context.Context, sessionID string, ttl time.Duration) error
	RevokeSessionAndFamily(ctx context.Context, sessionID, familyID string, ttl time.Duration) error
	SessionRevoked(ctx context.Context, sessionID string) (bool, error)
	RevokeAccess(ctx context.Context, jti string, ttl time.Duration) error
	AccessRevoked(ctx context.Context, jti string) (bool, error)
	ConsumeStepUp(ctx context.Context, jti string, ttl time.Duration) (bool, error)
}

type memoryJTIEntry struct {
	expiresAt time.Time
}

// MemoryJTIStore is a process-local store (tests / Redis-less single instance without JWT issuance).
type MemoryJTIStore struct {
	m         sync.Map
	revoked   sync.Map
	ops       atomic.Uint64
	purgeMu   sync.Mutex
	lastPurge time.Time
}

// ConsumeOnce implements JTIStore with TTL-aware one-time consumption.
func (s *MemoryJTIStore) ConsumeOnce(_ context.Context, jti string, ttl time.Duration) (bool, error) {
	now := time.Now().UTC()
	if ttl <= 0 {
		ttl = time.Second
	}
	ent := memoryJTIEntry{expiresAt: now.Add(ttl)}
	for {
		if s.liveEntry(jti, now) {
			return false, nil
		}
		actual, loaded := s.m.LoadOrStore(jti, ent)
		if !loaded {
			s.maybePurgeExpired(now)
			return true, nil
		}
		existing := actual.(memoryJTIEntry)
		if now.Before(existing.expiresAt) {
			return false, nil
		}
		_ = s.m.CompareAndDelete(jti, actual)
	}
}

func (s *MemoryJTIStore) liveEntry(jti string, now time.Time) bool {
	return entryLive(liveLookup{m: &s.m, key: jti, now: now})
}

func (s *MemoryJTIStore) revokedLive(key string) bool {
	return entryLive(liveLookup{m: &s.revoked, key: key, now: time.Now().UTC()})
}

type liveLookup struct {
	m   *sync.Map
	key string
	now time.Time
}

func entryLive(look liveLookup) bool {
	v, ok := look.m.Load(look.key)
	if !ok {
		return false
	}
	ent := v.(memoryJTIEntry)
	if look.now.Before(ent.expiresAt) {
		return true
	}
	_ = look.m.CompareAndDelete(look.key, v)
	return false
}

func (s *MemoryJTIStore) storeRevoked(marker memoryRevokeMarker, emptyID bool) error {
	if emptyID {
		return nil
	}
	ttl := marker.ttl
	if ttl <= 0 {
		ttl = time.Second
	}
	s.revoked.Store(marker.key, memoryJTIEntry{expiresAt: time.Now().UTC().Add(ttl)})
	return nil
}

type memoryRevokeMarker struct {
	key string
	ttl time.Duration
}

func (s *MemoryJTIStore) RevokeSession(_ context.Context, sessionID string, ttl time.Duration) error {
	return s.storeRevoked(memoryRevokeMarker{key: "session:" + sessionID, ttl: ttl}, sessionID == "")
}

func (s *MemoryJTIStore) RevokeAccess(_ context.Context, jti string, ttl time.Duration) error {
	return s.storeRevoked(memoryRevokeMarker{key: "access:" + jti, ttl: ttl}, jti == "")
}

func (s *MemoryJTIStore) SessionRevoked(_ context.Context, sessionID string) (bool, error) {
	return s.revokedLive("session:" + sessionID), nil
}

func (s *MemoryJTIStore) AccessRevoked(_ context.Context, jti string) (bool, error) {
	return s.revokedLive("access:" + jti), nil
}

func (s *MemoryJTIStore) ConsumeStepUp(ctx context.Context, jti string, ttl time.Duration) (bool, error) {
	return s.ConsumeOnce(ctx, "step-up:"+jti, ttl)
}

// maybePurgeExpired amortizes full-map scans: every N successful inserts and at most
// once per memoryJTIPurgeMinInterval. Hot-path ConsumeOnce stays O(1) expected.
func (s *MemoryJTIStore) maybePurgeExpired(now time.Time) {
	if s.ops.Add(1)%memoryJTIPurgeEveryN != 0 {
		return
	}
	s.purgeMu.Lock()
	defer s.purgeMu.Unlock()
	if !s.lastPurge.IsZero() && now.Sub(s.lastPurge) < memoryJTIPurgeMinInterval {
		return
	}
	s.lastPurge = now
	s.purgeExpiredLocked(now)
}

func (s *MemoryJTIStore) purgeExpiredLocked(now time.Time) {
	s.m.Range(func(key, value any) bool {
		ent := value.(memoryJTIEntry)
		if !now.Before(ent.expiresAt) {
			s.m.Delete(key)
		}
		return true
	})
	s.revoked.Range(func(key, value any) bool {
		ent := value.(memoryJTIEntry)
		if !now.Before(ent.expiresAt) {
			s.revoked.Delete(key)
		}
		return true
	})
}

// RevokeFamily implements JTIStore.
func (s *MemoryJTIStore) RevokeFamily(_ context.Context, familyID string, ttl time.Duration) error {
	if familyID == "" {
		return nil
	}
	if ttl <= 0 {
		ttl = time.Second
	}
	now := time.Now().UTC()
	s.revoked.Store(familyID, memoryJTIEntry{expiresAt: now.Add(ttl)})
	s.maybePurgeExpired(now)
	return nil
}

// FamilyRevoked implements JTIStore.
func (s *MemoryJTIStore) FamilyRevoked(_ context.Context, familyID string) (bool, error) {
	if familyID == "" {
		return false, nil
	}
	return entryLive(liveLookup{m: &s.revoked, key: familyID, now: time.Now().UTC()}), nil
}

// RevokeSessionAndFamily marks both session and refresh-family state for the same TTL.
func (s *MemoryJTIStore) RevokeSessionAndFamily(ctx context.Context, sessionID, familyID string, ttl time.Duration) error {
	if sessionID == "" {
		return fmt.Errorf("sessionjwt: empty session id")
	}
	if ttl <= 0 {
		ttl = time.Second
	}
	if err := s.RevokeSession(ctx, sessionID, ttl); err != nil {
		return err
	}
	return s.RevokeFamily(ctx, familyID, ttl)
}

// RedisJTIStore persists refresh JTI consumption with TTL = remaining token life.
type RedisJTIStore struct {
	client redis.UniversalClient
}

// NewRedisJTIStore constructs a Redis-backed JTI store.
func NewRedisJTIStore(client redis.UniversalClient) (*RedisJTIStore, error) {
	if client == nil {
		return nil, fmt.Errorf("sessionjwt: nil redis client")
	}
	return &RedisJTIStore{client: client}, nil
}

// ConsumeOnce implements JTIStore via SET NX EX.
func (s *RedisJTIStore) ConsumeOnce(ctx context.Context, jti string, ttl time.Duration) (bool, error) {
	if ttl <= 0 {
		ttl = time.Second
	}
	ok, err := s.client.SetNX(ctx, refreshJTIKeyPrefix+jti, "1", ttl).Result()
	if err != nil {
		return false, fmt.Errorf("sessionjwt: refresh jti consume: %w", err)
	}
	return ok, nil
}

// RevokeFamily implements JTIStore via SET EX on a family key.
func (s *RedisJTIStore) RevokeFamily(ctx context.Context, familyID string, ttl time.Duration) error {
	if familyID == "" {
		return nil
	}
	if ttl <= 0 {
		ttl = time.Second
	}
	if err := s.client.Set(ctx, refreshFamilyRevokedKeyPrefix+familyID, "1", ttl).Err(); err != nil {
		return fmt.Errorf("sessionjwt: revoke refresh family: %w", err)
	}
	return nil
}

// FamilyRevoked implements JTIStore.
func (s *RedisJTIStore) FamilyRevoked(ctx context.Context, familyID string) (bool, error) {
	if familyID == "" {
		return false, nil
	}
	n, err := s.client.Exists(ctx, refreshFamilyRevokedKeyPrefix+familyID).Result()
	if err != nil {
		return false, fmt.Errorf("sessionjwt: family revoked check: %w", err)
	}
	return n > 0, nil
}

func (s *RedisJTIStore) RevokeSession(ctx context.Context, sessionID string, ttl time.Duration) error {
	if sessionID == "" {
		return nil
	}
	if ttl <= 0 {
		ttl = time.Second
	}
	return s.client.Set(ctx, sessionRevokedKeyPrefix+sessionID, "1", ttl).Err()
}

// RevokeSessionAndFamily writes both revocation markers atomically in Redis.
func (s *RedisJTIStore) RevokeSessionAndFamily(ctx context.Context, sessionID, familyID string, ttl time.Duration) error {
	if sessionID == "" {
		return fmt.Errorf("sessionjwt: empty session id")
	}
	if ttl <= 0 {
		ttl = time.Second
	}
	if familyID == "" {
		return s.RevokeSession(ctx, sessionID, ttl)
	}
	const script = `
redis.call('SET', KEYS[1], '1', 'PX', ARGV[1])
redis.call('SET', KEYS[2], '1', 'PX', ARGV[1])
return 1
`
	ttlMilliseconds := ttl.Milliseconds()
	if ttlMilliseconds < 1 {
		ttlMilliseconds = 1
	}
	_, err := s.client.Eval(
		ctx,
		script,
		[]string{sessionRevokedKeyPrefix + sessionID, refreshFamilyRevokedKeyPrefix + familyID},
		ttlMilliseconds,
	).Result()
	if err != nil {
		return fmt.Errorf("sessionjwt: atomically revoke session and family: %w", err)
	}
	return nil
}

func (s *RedisJTIStore) SessionRevoked(ctx context.Context, sessionID string) (bool, error) {
	n, err := s.client.Exists(ctx, sessionRevokedKeyPrefix+sessionID).Result()
	return n > 0, err
}

func (s *RedisJTIStore) RevokeAccess(ctx context.Context, jti string, ttl time.Duration) error {
	if jti == "" {
		return nil
	}
	if ttl <= 0 {
		ttl = time.Second
	}
	return s.client.Set(ctx, accessRevokedKeyPrefix+jti, "1", ttl).Err()
}

func (s *RedisJTIStore) AccessRevoked(ctx context.Context, jti string) (bool, error) {
	n, err := s.client.Exists(ctx, accessRevokedKeyPrefix+jti).Result()
	return n > 0, err
}

func (s *RedisJTIStore) ConsumeStepUp(ctx context.Context, jti string, ttl time.Duration) (bool, error) {
	if ttl <= 0 {
		ttl = time.Second
	}
	return s.client.SetNX(ctx, stepUpJTIKeyPrefix+jti, "1", ttl).Result()
}
