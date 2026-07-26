package idempotency

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
)

// RedisStore implements Store with Redis SETNX + GET.
type RedisStore struct {
	client redis.UniversalClient
	ttl    time.Duration
}

// NewRedisStore returns an org-scoped idempotency store backed by Redis.
func NewRedisStore(client redis.UniversalClient, cfg Config) *RedisStore {
	ttl := cfg.TTL
	if ttl <= 0 {
		ttl = defaultTTL
	}
	return &RedisStore{client: client, ttl: ttl}
}

// Claim implements Store.
func (s *RedisStore) Claim(ctx context.Context, orgID uuid.UUID, key, fingerprint string) (Outcome, error) {
	redisKey := RedisKey(orgID, key)
	pending, err := encodeRecord(Record{State: StatePending, Fingerprint: fingerprint})
	if err != nil {
		return Outcome{}, fmt.Errorf("idempotency.Claim encode: %w", err)
	}
	ok, err := s.client.SetNX(ctx, redisKey, pending, s.ttl).Result()
	if err != nil {
		return Outcome{}, fmt.Errorf("idempotency.Claim SETNX: %w", err)
	}
	if ok {
		return Outcome{Kind: KindMiss, Record: Record{State: StatePending, Fingerprint: fingerprint}}, nil
	}
	return s.inspectExisting(ctx, redisKey, fingerprint)
}

func (s *RedisStore) inspectExisting(ctx context.Context, redisKey, fingerprint string) (Outcome, error) {
	raw, err := s.client.Get(ctx, redisKey).Bytes()
	if err == redis.Nil {
		// Race: key expired between SETNX miss and GET — treat as miss by reclaiming.
		return s.reclaim(ctx, redisKey, fingerprint)
	}
	if err != nil {
		return Outcome{}, fmt.Errorf("idempotency.Claim GET: %w", err)
	}
	rec, err := decodeRecord(raw)
	if err != nil {
		return Outcome{}, fmt.Errorf("idempotency.Claim decode: %w", err)
	}
	if rec.Fingerprint != fingerprint {
		return Outcome{Kind: KindConflict, Record: rec}, nil
	}
	if rec.State == StateCompleted {
		return Outcome{Kind: KindHit, Record: rec}, nil
	}
	return Outcome{Kind: KindInProgress, Record: rec}, nil
}

func (s *RedisStore) reclaim(ctx context.Context, redisKey, fingerprint string) (Outcome, error) {
	pending, err := encodeRecord(Record{State: StatePending, Fingerprint: fingerprint})
	if err != nil {
		return Outcome{}, err
	}
	ok, err := s.client.SetNX(ctx, redisKey, pending, s.ttl).Result()
	if err != nil {
		return Outcome{}, fmt.Errorf("idempotency.Claim reclaim SETNX: %w", err)
	}
	if ok {
		return Outcome{Kind: KindMiss, Record: Record{State: StatePending, Fingerprint: fingerprint}}, nil
	}
	return Outcome{Kind: KindInProgress}, nil
}

// Commit implements Store.
func (s *RedisStore) Commit(ctx context.Context, orgID uuid.UUID, key string, rec Record) error {
	rec.State = StateCompleted
	raw, err := encodeRecord(rec)
	if err != nil {
		return fmt.Errorf("idempotency.Commit encode: %w", err)
	}
	if err := s.client.Set(ctx, RedisKey(orgID, key), raw, s.ttl).Err(); err != nil {
		return fmt.Errorf("idempotency.Commit SET: %w", err)
	}
	return nil
}

func encodeRecord(rec Record) (string, error) {
	b, err := json.Marshal(rec)
	if err != nil {
		return "", err
	}
	return string(b), nil
}

func decodeRecord(raw []byte) (Record, error) {
	var rec Record
	if err := json.Unmarshal(raw, &rec); err != nil {
		return Record{}, err
	}
	return rec, nil
}

// Ensure RedisStore satisfies Store.
var _ Store = (*RedisStore)(nil)
