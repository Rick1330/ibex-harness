package idempotency

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"time"

	"github.com/redis/go-redis/v9"
)

// errCASSkip means the key is no longer owned by this claim (no-op success).
var errCASSkip = errors.New("idempotency: cas skip")

// RedisStore implements Store with Redis SETNX + optimistic CAS.
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
func (s *RedisStore) Claim(ctx context.Context, tok Token, fingerprint string) (Outcome, error) {
	redisKey := RedisKey(tok)
	out, err := s.tryClaimPending(ctx, redisKey, fingerprint)
	if err != nil {
		return Outcome{}, fmt.Errorf("idempotency.Claim SETNX: %w", err)
	}
	if out.Kind == KindMiss {
		return out, nil
	}
	return s.inspectExisting(ctx, redisKey, fingerprint)
}

func (s *RedisStore) inspectExisting(ctx context.Context, redisKey, fingerprint string) (Outcome, error) {
	raw, err := s.client.Get(ctx, redisKey).Bytes()
	if errors.Is(err, redis.Nil) {
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
	out, err := s.tryClaimPending(ctx, redisKey, fingerprint)
	if err != nil {
		return Outcome{}, fmt.Errorf("idempotency.Claim reclaim SETNX: %w", err)
	}
	return out, nil
}

func (s *RedisStore) tryClaimPending(ctx context.Context, redisKey, fingerprint string) (Outcome, error) {
	pending, err := encodeRecord(pendingRecord(fingerprint))
	if err != nil {
		return Outcome{}, err
	}
	ok, err := s.client.SetNX(ctx, redisKey, pending, s.pendingTTL).Result()
	if err != nil {
		return Outcome{}, err
	}
	if ok {
		return Outcome{Kind: KindMiss, Record: pendingRecord(fingerprint)}, nil
	}
	return Outcome{Kind: KindInProgress}, nil
}

// Commit implements Store.
func (s *RedisStore) Commit(ctx context.Context, tok Token, rec Record) error {
	rec.Version = CurrentRecordVersion
	rec.State = StateCompleted
	raw, err := encodeRecord(rec)
	if err != nil {
		return fmt.Errorf("idempotency.Commit encode: %w", err)
	}
	redisKey := RedisKey(tok)
	err = s.casPending(ctx, redisKey, rec.Fingerprint, func(pipe redis.Pipeliner) error {
		pipe.Set(ctx, redisKey, raw, s.ttl)
		return nil
	})
	if err != nil {
		return fmt.Errorf("idempotency.Commit: %w", err)
	}
	return nil
}

// Release implements Store.
func (s *RedisStore) Release(ctx context.Context, tok Token, fingerprint string) error {
	redisKey := RedisKey(tok)
	err := s.casPending(ctx, redisKey, fingerprint, func(pipe redis.Pipeliner) error {
		pipe.Del(ctx, redisKey)
		return nil
	})
	if err != nil {
		return fmt.Errorf("idempotency.Release: %w", err)
	}
	return nil
}

func (s *RedisStore) casPending(
	ctx context.Context,
	redisKey, fingerprint string,
	mutate func(redis.Pipeliner) error,
) error {
	const maxTries = 3
	own := pendingOwner{redisKey: redisKey, fingerprint: fingerprint}
	for try := 0; try < maxTries; try++ {
		err := s.client.Watch(ctx, func(tx *redis.Tx) error {
			return s.casPendingTx(ctx, tx, own, mutate)
		}, redisKey)
		if err == nil || errors.Is(err, errCASSkip) {
			return nil
		}
		if errors.Is(err, redis.TxFailedErr) {
			continue
		}
		return err
	}
	return redis.TxFailedErr
}

type pendingOwner struct {
	redisKey, fingerprint string
}

func (s *RedisStore) casPendingTx(
	ctx context.Context,
	tx *redis.Tx,
	own pendingOwner,
	mutate func(redis.Pipeliner) error,
) error {
	cur, err := tx.Get(ctx, own.redisKey).Bytes()
	if errors.Is(err, redis.Nil) {
		return errCASSkip
	}
	if err != nil {
		return err
	}
	existing, err := decodeRecord(cur)
	if err != nil {
		return err
	}
	if existing.State != StatePending || existing.Fingerprint != own.fingerprint {
		return errCASSkip
	}
	_, err = tx.TxPipelined(ctx, mutate)
	return err
}

func pendingRecord(fingerprint string) Record {
	return Record{
		Version:     CurrentRecordVersion,
		State:       StatePending,
		Fingerprint: fingerprint,
	}
}

func encodeRecord(rec Record) (string, error) {
	if rec.Version == 0 {
		rec.Version = CurrentRecordVersion
	}
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
	if rec.Version != CurrentRecordVersion {
		return Record{}, fmt.Errorf("%w: got %d", ErrUnsupportedVersion, rec.Version)
	}
	return rec, nil
}

// PendingTTL returns the in-flight claim TTL (tests).
func (s *RedisStore) PendingTTL() time.Duration { return s.pendingTTL }

// Ensure RedisStore satisfies Store.
var _ Store = (*RedisStore)(nil)
