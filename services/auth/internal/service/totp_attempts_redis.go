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

func (r *RedisTOTPAttempts) failKey(ref TenantRef) string {
	return totpFailKeyPrefix + totpAttemptKey(ref)
}

func (r *RedisTOTPAttempts) lockKey(ref TenantRef) string {
	return totpLockKeyPrefix + totpAttemptKey(ref)
}

// Allow reserves one attempt atomically before verification (fail-closed on Redis errors).
func (r *RedisTOTPAttempts) Allow(ref TenantRef) error {
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	n, err := totpReserveScript.Run(
		ctx, r.client,
		[]string{r.failKey(ref), r.lockKey(ref)},
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

// Fail is intentional no-op: Allow already reserved the attempt for this verification.
func (r *RedisTOTPAttempts) Fail(ref TenantRef) {
	_ = ref
	// Deliberate no-op — reservation counted in Allow; do not double-count.
}

// totpReleaseScript undoes one Allow reservation (DECR) without clearing lockout.
var totpReleaseScript = redis.NewScript(`
local failKey = KEYS[1]
local n = redis.call('DECR', failKey)
if n <= 0 then
  redis.call('DEL', failKey)
  return 0
end
return n
`)

// Release undoes a prior Allow reservation after non-invalid-code failures.
func (r *RedisTOTPAttempts) Release(ref TenantRef) {
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	_, _ = totpReleaseScript.Run(ctx, r.client, []string{r.failKey(ref)}).Int64()
}

// Reset clears reservations after successful verification.
func (r *RedisTOTPAttempts) Reset(ref TenantRef) {
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	_ = r.client.Del(ctx, r.failKey(ref), r.lockKey(ref)).Err()
}

// Ensure RedisTOTPAttempts satisfies the attempt gate used by TotpService.
var _ totpAttemptGate = (*RedisTOTPAttempts)(nil)
