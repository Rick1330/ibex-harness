package idempotency

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"hash/fnv"
	"strings"
	"time"

	"github.com/redis/go-redis/v9"
)

// errCASSkip means the key is no longer owned by this claim (no-op success).
var errCASSkip = errors.New("idempotency: cas skip")

// pendingOwner identifies a Redis key and caller fingerprint for claim/CAS paths.
type pendingOwner struct {
	redisKey    string
	fingerprint Fingerprint
}

// RedisStore implements Store with Redis SETNX + optimistic CAS.
type RedisStore struct {
	client     redis.UniversalClient
	ttl        time.Duration
	pendingTTL time.Duration
}

// NewRedisStore returns an org-scoped idempotency store backed by Redis.
func NewRedisStore(client redis.UniversalClient, cfg Config) (*RedisStore, error) {
	if client == nil {
		return nil, fmt.Errorf("idempotency: nil redis client")
	}
	cfg = cfg.withDefaults()
	return &RedisStore{client: client, ttl: cfg.TTL, pendingTTL: cfg.PendingTTL}, nil
}

// Claim implements Store.
func (rs *RedisStore) Claim(ctx context.Context, tok Token, fingerprint Fingerprint) (Outcome, error) {
	own := pendingOwner{redisKey: RedisKey(tok), fingerprint: fingerprint}
	out, err := rs.tryClaimPending(ctx, own)
	if err != nil {
		return Outcome{}, wrapRedisOpErr("idempotency.Claim", own, err)
	}
	if out.Kind == KindMiss {
		return out, nil
	}
	return rs.inspectExisting(ctx, own)
}

func (rs *RedisStore) inspectExisting(ctx context.Context, own pendingOwner) (Outcome, error) {
	raw, err := rs.client.Get(ctx, own.redisKey).Bytes()
	if errors.Is(err, redis.Nil) {
		return rs.reclaim(ctx, own)
	}
	if err != nil {
		return Outcome{}, wrapRedisOpErr("idempotency.Claim GET", own, err)
	}
	rec, err := decodeRecord(raw)
	if err != nil {
		return Outcome{}, wrapRedisOpErr("idempotency.Claim decode", own, err)
	}
	if rec.Fingerprint != own.fingerprint {
		return Outcome{Kind: KindConflict, Record: rec}, nil
	}
	if rec.State == StateCompleted {
		return Outcome{Kind: KindHit, Record: rec}, nil
	}
	return Outcome{Kind: KindInProgress, Record: rec}, nil
}

func (rs *RedisStore) reclaim(ctx context.Context, own pendingOwner) (Outcome, error) {
	out, err := rs.tryClaimPending(ctx, own)
	if err != nil {
		return Outcome{}, wrapRedisOpErr("idempotency.Claim reclaim", own, err)
	}
	if out.Kind != KindMiss {
		return rs.inspectExisting(ctx, own)
	}
	return out, nil
}

func (rs *RedisStore) tryClaimPending(ctx context.Context, own pendingOwner) (Outcome, error) {
	pending, err := encodeRecord(pendingRecord(own.fingerprint))
	if err != nil {
		return Outcome{}, fmt.Errorf("encode pending: %w", err)
	}
	ok, err := rs.client.SetNX(ctx, own.redisKey, pending, rs.pendingTTL).Result()
	if err != nil {
		return Outcome{}, fmt.Errorf("SETNX: %w", err)
	}
	if ok {
		return Outcome{Kind: KindMiss, Record: pendingRecord(own.fingerprint)}, nil
	}
	return Outcome{Kind: KindInProgress}, nil
}

// Commit implements Store.
func (rs *RedisStore) Commit(ctx context.Context, tok Token, rec Record) error {
	own := pendingOwner{redisKey: RedisKey(tok), fingerprint: rec.Fingerprint}
	rec.Version = CurrentRecordVersion
	rec.State = StateCompleted
	raw, err := encodeRecord(rec)
	if err != nil {
		return wrapRedisOpErr("idempotency.Commit encode", own, err)
	}
	err = rs.casPending(ctx, own, func(pipe redis.Pipeliner) error {
		pipe.Set(ctx, own.redisKey, raw, rs.ttl)
		return nil
	})
	if err != nil {
		return wrapRedisOpErr("idempotency.Commit", own, err)
	}
	return nil
}

// Release implements Store.
func (rs *RedisStore) Release(ctx context.Context, tok Token, fingerprint Fingerprint) error {
	own := pendingOwner{redisKey: RedisKey(tok), fingerprint: fingerprint}
	err := rs.casPending(ctx, own, func(pipe redis.Pipeliner) error {
		pipe.Del(ctx, own.redisKey)
		return nil
	})
	if err != nil {
		return wrapRedisOpErr("idempotency.Release", own, err)
	}
	return nil
}

func (rs *RedisStore) casPending(
	ctx context.Context,
	own pendingOwner,
	mutate func(redis.Pipeliner) error,
) error {
	const maxTries = 3
	for try := 0; try < maxTries; try++ {
		err := rs.client.Watch(ctx, func(tx *redis.Tx) error {
			return rs.casPendingTx(ctx, tx, own, mutate)
		}, own.redisKey)
		if err == nil || errors.Is(err, errCASSkip) {
			return nil
		}
		if errors.Is(err, redis.TxFailedErr) {
			continue
		}
		return wrapRedisOpErr("idempotency.casPending watch", own, err)
	}
	return wrapRedisOpErr("idempotency.casPending watch retries", own, redis.TxFailedErr)
}

func (rs *RedisStore) casPendingTx(
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

func pendingRecord(fingerprint Fingerprint) Record {
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

func wrapRedisOpErr(op string, own pendingOwner, err error) error {
	return fmt.Errorf("%s key=%s: %w", op, safeRedisKey(own.redisKey), err)
}

func safeRedisKey(redisKey string) string {
	parts := strings.SplitN(redisKey, ":", 3)
	if len(parts) != 3 {
		return "idempotency:unknown"
	}
	h := fnv.New64a()
	_, _ = h.Write([]byte(parts[2]))
	return fmt.Sprintf("%s:%s:%x", parts[0], parts[1], h.Sum64())
}

// PendingTTL returns the in-flight claim TTL (tests).
func (rs *RedisStore) PendingTTL() time.Duration { return rs.pendingTTL }

// Ensure RedisStore satisfies Store.
var _ Store = (*RedisStore)(nil)
