//go:build integration

package integrationtest

import (
	"testing"

	"github.com/Rick1330/ibex-harness/infra/testing/testutil"
	"github.com/alicebob/miniredis/v2"
	"github.com/redis/go-redis/v9"
)

func TestIntegration_StartAuthGRPC(t *testing.T) {
	dsn, cleanup := testutil.SetupPostgres(t)
	defer cleanup()

	fx := StartAuthGRPC(t, dsn)
	if fx.Addr == "" || fx.Client == nil {
		t.Fatal("incomplete fixture")
	}

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
	defer func() { _ = client.Close() }()

	fx := StartAuthGRPCWithRedis(t, dsn, client)
	if fx.Addr == "" || fx.Client == nil || fx.tokenSvc == nil {
		t.Fatal("incomplete fixture")
	}
	fx.WaitPendingPublishes()
	fx.Close()
}
