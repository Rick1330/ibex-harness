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

// MemoryJTIStore is a process-local store (tests / Redis-less single instance).
type MemoryJTIStore struct {
	m sync.Map
}

// ConsumeOnce implements JTIStore.
func (s *MemoryJTIStore) ConsumeOnce(_ context.Context, jti string, _ time.Duration) (bool, error) {
	_, loaded := s.m.LoadOrStore(jti, struct{}{})
	return !loaded, nil
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
