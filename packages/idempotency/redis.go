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
	client     redis.UniversalClient
	ttl        time.Duration
	pendingTTL time.Duration
}

// NewRedisStore returns an org-scoped idempotency store backed by Redis.
func NewRedisStore(client redis.UniversalClient, cfg Config) *RedisStore {
	cfg = cfg.withDefaults()
	return &RedisStore{client: client, ttl: cfg.TTL, pendingTTL: cfg.PendingTTL}
}

// Claim implements Store.
func (s *RedisStore) Claim(ctx context.Context, orgID uuid.UUID, key, fingerprint string) (Outcome, error) {
	redisKey := RedisKey(orgID, key)
	pending := mustEncodeRecord(pendingRecord(fingerprint))
	ok, err := s.client.SetNX(ctx, redisKey, pending, s.pendingTTL).Result()
	if err != nil {
		return Outcome{}, fmt.Errorf("idempotency.Claim SETNX: %w", err)
	}
	if ok {
		return Outcome{Kind: KindMiss, Record: pendingRecord(fingerprint)}, nil
	}
	return s.inspectExisting(ctx, redisKey, fingerprint)
}

func (s *RedisStore) inspectExisting(ctx context.Context, redisKey, fingerprint string) (Outcome, error) {
	raw, err := s.client.Get(ctx, redisKey).Bytes()
	if err == redis.Nil {
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
	pending := mustEncodeRecord(pendingRecord(fingerprint))
	ok, err := s.client.SetNX(ctx, redisKey, pending, s.pendingTTL).Result()
	if err != nil {
		return Outcome{}, fmt.Errorf("idempotency.Claim reclaim SETNX: %w", err)
	}
	if ok {
		return Outcome{Kind: KindMiss, Record: pendingRecord(fingerprint)}, nil
	}
	return Outcome{Kind: KindInProgress}, nil
}

// Commit implements Store.
func (s *RedisStore) Commit(ctx context.Context, orgID uuid.UUID, key string, rec Record) error {
	rec.Version = CurrentRecordVersion
	rec.State = StateCompleted
	raw := mustEncodeRecord(rec)
	if err := s.client.Set(ctx, RedisKey(orgID, key), raw, s.ttl).Err(); err != nil {
		return fmt.Errorf("idempotency.Commit SET: %w", err)
	}
	return nil
}

// Release implements Store.
func (s *RedisStore) Release(ctx context.Context, orgID uuid.UUID, key string) error {
	if err := s.client.Del(ctx, RedisKey(orgID, key)).Err(); err != nil {
		return fmt.Errorf("idempotency.Release DEL: %w", err)
	}
	return nil
}

func pendingRecord(fingerprint string) Record {
	return Record{
		Version:     CurrentRecordVersion,
		State:       StatePending,
		Fingerprint: fingerprint,
	}
}

func mustEncodeRecord(rec Record) string {
	if rec.Version == 0 {
		rec.Version = CurrentRecordVersion
	}
	b, err := json.Marshal(rec)
	if err != nil {
		// Record is a closed schema; marshal failures indicate programmer error.
		panic("idempotency: encode record: " + err.Error())
	}
	return string(b)
}

func decodeRecord(raw []byte) (Record, error) {
	var rec Record
	if err := json.Unmarshal(raw, &rec); err != nil {
		return Record{}, err
	}
	if rec.Version != CurrentRecordVersion {
		return Record{}, fmt.Errorf("%w: got %d", ErrUnsupportedVersion, rec.Version)
	}
	return rec, nil
}

// PendingTTL returns the in-flight claim TTL (tests).
func (s *RedisStore) PendingTTL() time.Duration { return s.pendingTTL }

// Ensure RedisStore satisfies Store.
var _ Store = (*RedisStore)(nil)
