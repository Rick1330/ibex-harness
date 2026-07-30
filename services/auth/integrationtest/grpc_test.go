//go:build integration

package integrationtest

import (
	"testing"

	"github.com/Rick1330/ibex-harness/infra/testing/testutil"
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
