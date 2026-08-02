//go:build integration

package integrationtest

import (
	"fmt"
	"testing"

	"github.com/Rick1330/ibex-harness/infra/testing/testutil"
	"github.com/Rick1330/ibex-harness/packages/ratelimit"
	"github.com/alicebob/miniredis/v2"
	"github.com/redis/go-redis/v9"
)

func assertAuthGRPCFixture(t *testing.T, fx *AuthGRPCFixture, wantTokenSvc bool) {
	t.Helper()
	if fx.Addr == "" {
		t.Fatal("fixture Addr must be set")
	}
	if fx.Client == nil {
		t.Fatal("fixture Client must be set")
	}
	if wantTokenSvc && fx.tokenSvc == nil {
		t.Fatal("fixture tokenSvc must be set")
	}
}

func TestIntegration_StartAuthGRPC(t *testing.T) {
	dsn, cleanup := testutil.SetupPostgres(t)
	defer cleanup()

	fx := StartAuthGRPC(t, dsn)
	assertAuthGRPCFixture(t, fx, false)

	var nilFx *AuthGRPCFixture
	nilFx.WaitPendingPublishes()
	fx.WaitPendingPublishes()
	fx.Close()
}

func TestIntegration_StartAuthGRPCWithRedis(t *testing.T) {
	dsn, cleanup := testutil.SetupPostgres(t)
	defer cleanup()

	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() {
		if err := client.Close(); err != nil {
			t.Errorf("close redis client: %v", err)
		}
	})

	fx := StartAuthGRPCWithRedis(t, dsn, client)
	assertAuthGRPCFixture(t, fx, true)
	fx.WaitPendingPublishes()
	fx.Close()
}

func TestIntegration_StartAuthGRPCWithValidateLimiter(t *testing.T) {
	dsn, cleanup := testutil.SetupPostgres(t)
	defer cleanup()

	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })

	limiter, err := ratelimit.NewRedisKeyed(client, ratelimit.RedisKeyedConfig{
		DefaultRPM: 100,
		KeyPrefix:  "ratelimit:auth:validate:fixture",
	})
	if err != nil {
		t.Fatal(err)
	}
	fx := StartAuthGRPCWithValidateLimiter(t, dsn, limiter)
	assertAuthGRPCFixture(t, fx, true)
	fx.Close()
}

func TestIntegration_StartAuthGRPC_NilGuards(t *testing.T) {
	t.Parallel()
	assertStartFatal(t, func(tb testing.TB) {
		StartAuthGRPCWithRedis(tb, "postgres://unused", nil)
	})
	assertStartFatal(t, func(tb testing.TB) {
		StartAuthGRPCWithValidateLimiter(tb, "postgres://unused", nil)
	})
}

type fatalRecorder struct {
	testing.TB
	msg string
}

func (f *fatalRecorder) Helper() {}
func (f *fatalRecorder) Fatal(args ...any) {
	f.msg = fmt.Sprint(args...)
	panic("fatal")
}
func (f *fatalRecorder) Fatalf(format string, args ...any) {
	f.msg = fmt.Sprintf(format, args...)
	panic("fatal")
}

func assertStartFatal(t *testing.T, run func(testing.TB)) {
	t.Helper()
	rec := &fatalRecorder{TB: t}
	defer func() {
		if recover() == nil {
			t.Fatal("expected Fatal from nil guard")
		}
		if rec.msg == "" {
			t.Fatal("expected fatal message")
		}
	}()
	run(rec)
}
