//go:build integration

package auth_test

import (
	"context"
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/infra/testing/testutil"
	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"github.com/Rick1330/ibex-harness/packages/ratelimit"
	"github.com/Rick1330/ibex-harness/services/auth/integrationtest"
	"github.com/alicebob/miniredis/v2"
	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

const validateRPCTimeout = 5 * time.Second

type errKeyedLimiter struct{}

func (errKeyedLimiter) CheckKey(context.Context, string) (ratelimit.Result, error) {
	return ratelimit.Result{}, errors.New("redis unavailable")
}

func validateTokenWithTimeout(t *testing.T, client authv1.AuthServiceClient, token string) error {
	t.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), validateRPCTimeout)
	defer cancel()
	_, err := client.ValidateToken(ctx, &authv1.ValidateTokenRequest{AccessToken: token})
	return err
}

func TestValidateToken_PeerRateLimit_ResourceExhausted(t *testing.T) {
	dsn, cleanup := testutil.SetupPostgres(t)
	defer cleanup()

	mr := miniredis.RunT(t)
	rdb := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() {
		if err := rdb.Close(); err != nil {
			t.Errorf("close redis: %v", err)
		}
	})

	limiter, err := ratelimit.NewRedisKeyed(rdb, ratelimit.RedisKeyedConfig{
		DefaultRPM: 1,
		KeyPrefix:  "ratelimit:auth:validate:it",
	})
	if err != nil {
		t.Fatalf("NewRedisKeyed: %v", err)
	}

	fx := integrationtest.StartAuthGRPCWithValidateLimiter(t, dsn, limiter)
	defer fx.Close()

	err = validateTokenWithTimeout(t, fx.Client, "not-a-pat")
	if status.Code(err) != codes.Unauthenticated {
		t.Fatalf("first: code=%v err=%v", status.Code(err), err)
	}

	err = validateTokenWithTimeout(t, fx.Client, "not-a-pat")
	if status.Code(err) != codes.ResourceExhausted {
		t.Fatalf("second: code=%v err=%v want ResourceExhausted", status.Code(err), err)
	}
}

func TestValidateToken_PeerRateLimit_FailOpen(t *testing.T) {
	dsn, cleanup := testutil.SetupPostgres(t)
	defer cleanup()

	fx := integrationtest.StartAuthGRPCWithValidateLimiter(t, dsn, errKeyedLimiter{})
	defer fx.Close()

	err := validateTokenWithTimeout(t, fx.Client, "not-a-pat")
	if status.Code(err) != codes.Unauthenticated {
		t.Fatalf("fail-open should reach validator; code=%v err=%v", status.Code(err), err)
	}
}

func TestValidateToken_OversizedPAT_Unauthenticated(t *testing.T) {
	dsn, cleanup := testutil.SetupPostgres(t)
	defer cleanup()

	fx := integrationtest.StartAuthGRPC(t, dsn)
	defer fx.Close()

	oversized := "ibex_pat_" + uuid.NewString() + "_" + strings.Repeat("a", 200)
	err := validateTokenWithTimeout(t, fx.Client, oversized)
	if status.Code(err) != codes.Unauthenticated {
		t.Fatalf("oversized PAT: code=%v err=%v", status.Code(err), err)
	}
}
