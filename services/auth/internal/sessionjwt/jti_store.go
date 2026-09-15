package sessionjwt

import (
	"context"
	"fmt"
	"sync"
	"time"

	"github.com/redis/go-redis/v9"
)

const refreshJTIKeyPrefix = "auth:session:refresh-jti:"

// JTIStore atomically tracks consumed refresh JTIs until expiry.
type JTIStore interface {
	// ConsumeOnce returns true when jti was recorded for the first time.
	ConsumeOnce(ctx context.Context, jti string, ttl time.Duration) (bool, error)
}

type memoryJTIEntry struct {
	expiresAt time.Time
}

// MemoryJTIStore is a process-local store (tests / Redis-less single instance).
type MemoryJTIStore struct {
	m sync.Map
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
			s.purgeExpired(now)
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
	v, ok := s.m.Load(jti)
	if !ok {
		return false
	}
	ent := v.(memoryJTIEntry)
	if now.Before(ent.expiresAt) {
		return true
	}
	_ = s.m.CompareAndDelete(jti, v)
	return false
}

func (s *MemoryJTIStore) purgeExpired(now time.Time) {
	s.m.Range(func(key, value any) bool {
		ent := value.(memoryJTIEntry)
		if !now.Before(ent.expiresAt) {
			s.m.Delete(key)
		}
		return true
	})
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
