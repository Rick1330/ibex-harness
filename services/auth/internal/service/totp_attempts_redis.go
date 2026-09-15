package service

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/redis/go-redis/v9"
)

const (
	totpFailKeyPrefix = "auth:totp:fail:"
	totpLockKeyPrefix = "auth:totp:lock:"
)

// ErrTOTPUnavailable is returned when the attempt gate cannot reach Redis.
var ErrTOTPUnavailable = errors.New("totp attempt store unavailable")

// RedisTOTPAttempts stores TOTP failure counts and lockouts in Redis.
type RedisTOTPAttempts struct {
	client   redis.UniversalClient
	maxFails int
	lockTTL  time.Duration
}

// totpReserveScript atomically checks lockout and reserves one attempt (INCR)
// before TOTP verification. Returns -1 when locked / over limit, else the count.
var totpReserveScript = redis.NewScript(`
local failKey = KEYS[1]
local lockKey = KEYS[2]
local maxFails = tonumber(ARGV[1])
local ttl = tonumber(ARGV[2])
if redis.call('EXISTS', lockKey) == 1 then
  return -1
end
local n = redis.call('INCR', failKey)
redis.call('EXPIRE', failKey, ttl)
if n > maxFails then
  redis.call('SET', lockKey, '1', 'EX', ttl)
  redis.call('DEL', failKey)
  return -1
end
return n
`)

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

// Allow reserves one attempt atomically before verification (fail-closed on Redis errors).
func (r *RedisTOTPAttempts) Allow(orgID, userID string) error {
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	n, err := totpReserveScript.Run(
		ctx, r.client,
		[]string{r.failKey(orgID, userID), r.lockKey(orgID, userID)},
		r.maxFails, int(r.lockTTL.Seconds()),
	).Int64()
	if err != nil {
		return ErrTOTPUnavailable
	}
	if n < 0 {
		return ErrTOTPLockedOut
	}
	return nil
}

// Fail is a no-op: Allow already reserved the attempt for this verification.
func (r *RedisTOTPAttempts) Fail(orgID, userID string) {}

// Reset clears reservations after successful verification.
func (r *RedisTOTPAttempts) Reset(orgID, userID string) {
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	_ = r.client.Del(ctx, r.failKey(orgID, userID), r.lockKey(orgID, userID)).Err()
}

// Ensure RedisTOTPAttempts satisfies the attempt gate used by TotpService.
var _ totpAttemptGate = (*RedisTOTPAttempts)(nil)
