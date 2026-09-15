package service

import (
	"context"
	"fmt"
	"time"

	"github.com/redis/go-redis/v9"
)

const (
	totpFailKeyPrefix = "auth:totp:fail:"
	totpLockKeyPrefix = "auth:totp:lock:"
)

// RedisTOTPAttempts stores TOTP failure counts and lockouts in Redis.
type RedisTOTPAttempts struct {
	client   redis.UniversalClient
	maxFails int
	lockTTL  time.Duration
}

// NewRedisTOTPAttempts constructs a shared attempt gate. client must be non-nil.
func NewRedisTOTPAttempts(client redis.UniversalClient, maxFails int, lockTTL time.Duration) (*RedisTOTPAttempts, error) {
	if client == nil {
		return nil, fmt.Errorf("totp attempts: nil redis client")
	}
	if maxFails < 1 {
		maxFails = totpMaxFailures
	}
	if lockTTL <= 0 {
		lockTTL = totpLockTTL
	}
	return &RedisTOTPAttempts{client: client, maxFails: maxFails, lockTTL: lockTTL}, nil
}

func (r *RedisTOTPAttempts) failKey(orgID, userID string) string {
	return totpFailKeyPrefix + totpAttemptKey(orgID, userID)
}

func (r *RedisTOTPAttempts) lockKey(orgID, userID string) string {
	return totpLockKeyPrefix + totpAttemptKey(orgID, userID)
}

// Allow implements totpAttemptGate.
func (r *RedisTOTPAttempts) Allow(orgID, userID string) error {
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	n, err := r.client.Exists(ctx, r.lockKey(orgID, userID)).Result()
	if err != nil {
		// Fail-open on Redis errors (same posture as ValidateToken rate limit).
		return nil
	}
	if n > 0 {
		return ErrTOTPLockedOut
	}
	return nil
}

// Fail implements totpAttemptGate.
func (r *RedisTOTPAttempts) Fail(orgID, userID string) {
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	failKey := r.failKey(orgID, userID)
	n, err := r.client.Incr(ctx, failKey).Result()
	if err != nil {
		return
	}
	_ = r.client.Expire(ctx, failKey, r.lockTTL).Err()
	if int(n) < r.maxFails {
		return
	}
	_ = r.client.Set(ctx, r.lockKey(orgID, userID), "1", r.lockTTL).Err()
	_ = r.client.Del(ctx, failKey).Err()
}

// Reset implements totpAttemptGate.
func (r *RedisTOTPAttempts) Reset(orgID, userID string) {
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	_ = r.client.Del(ctx, r.failKey(orgID, userID), r.lockKey(orgID, userID)).Err()
}

// Ensure RedisTOTPAttempts satisfies the attempt gate used by TotpService.
var _ totpAttemptGate = (*RedisTOTPAttempts)(nil)
