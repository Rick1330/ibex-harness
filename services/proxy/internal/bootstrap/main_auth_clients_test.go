package bootstrap

import (
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/infra/testing/grpctest"
	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/config"
	"github.com/alicebob/miniredis/v2"
	"github.com/redis/go-redis/v9"
)

func assertAuthClients(t *testing.T, b authClients, present bool) {
	t.Helper()
	checks := []struct {
		name string
		ok   bool
	}{
		{"validator", b.validator != nil},
		{"agentVerifier", b.agentVerifier != nil},
		{"client", b.client != nil},
		{"conn", b.conn != nil},
	}
	for _, c := range checks {
		if c.ok != present {
			want := "absent"
			if present {
				want = "present"
			}
			t.Fatalf("%s should be %s", c.name, want)
		}
	}
}

func assertCachingValidator(t *testing.T, v auth.TokenValidator) {
	t.Helper()
	if _, ok := v.(auth.CacheInvalidator); !ok {
		t.Fatal("expected caching validator implementing CacheInvalidator")
	}
}

func assertNotCachingValidator(t *testing.T, v auth.TokenValidator) {
	t.Helper()
	if _, ok := v.(auth.CacheInvalidator); ok {
		t.Fatal("expected unwrapped validator without CacheInvalidator")
	}
}

func testRedisClient(t *testing.T) *redis.Client {
	t.Helper()
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })
	return client
}

func setupAuthClientsForTest(t *testing.T, cache config.AuthCacheConfig, redisClient redis.UniversalClient) authClients {
	t.Helper()
	lis := grpctest.StartUnimplementedAuthServer(t)
	log := logger.Discard("proxy")
	cfg := config.Config{
		Environment:         "development",
		AuthGRPCAddr:        lis.Addr().String(),
		AuthValidateTimeout: time.Second,
		AuthCache:           cache,
	}

	clients, err := setupAuthClients(cfg, log, nil, redisClient)

	if err != nil {
		t.Fatalf("setupAuthClients: %v", err)
	}
	t.Cleanup(func() {
		if err := clients.conn.Close(); err != nil {
			t.Errorf("close conn: %v", err)
		}
	})
	return clients
}

func TestUnit_SetupAuthClients_GRPCOnly(t *testing.T) {
	t.Parallel()

	clients := setupAuthClientsForTest(t, config.AuthCacheConfig{}, nil)

	assertAuthClients(t, clients, true)
	assertNotCachingValidator(t, clients.validator)
}

func TestUnit_SetupAuthClients_WithAuthCache(t *testing.T) {
	t.Parallel()

	clients := setupAuthClientsForTest(t, validAuthCacheConfig(), testRedisClient(t))

	assertAuthClients(t, clients, true)
	assertCachingValidator(t, clients.validator)
}

func TestUnit_SetupAuthClients_AuthCacheSkippedWithoutRedis(t *testing.T) {
	t.Parallel()

	clients := setupAuthClientsForTest(t, validAuthCacheConfig(), nil)

	assertAuthClients(t, clients, true)
	assertNotCachingValidator(t, clients.validator)
}

func TestUnit_SetupAuthClients_EmptyAddr(t *testing.T) {
	t.Parallel()

	log := logger.Discard("proxy")

	clients, err := setupAuthClients(config.Config{AuthGRPCAddr: ""}, log, nil, nil)

	if err != nil {
		t.Fatalf("setupAuthClients: %v", err)
	}
	assertAuthClients(t, clients, false)
}

func TestUnit_SetupAuthClients_InvalidAuthCacheConfig(t *testing.T) {
	t.Parallel()

	lis := grpctest.StartUnimplementedAuthServer(t)
	log := logger.Discard("proxy")

	_, err := setupAuthClients(config.Config{
		Environment:         "development",
		AuthGRPCAddr:        lis.Addr().String(),
		AuthValidateTimeout: time.Second,
		AuthCache: config.AuthCacheConfig{
			Enabled:     true,
			LRUCapacity: -1,
		},
	}, log, nil, testRedisClient(t))

	if err == nil {
		t.Fatal("expected auth cache config error")
	}
}

func TestUnit_AuthTransportCredentials_DevelopmentInsecure(t *testing.T) {
	t.Parallel()

	creds := authTransportCredentials("development")

	if creds.Info().SecurityProtocol != "insecure" {
		t.Fatalf("protocol=%q", creds.Info().SecurityProtocol)
	}
	tlsCreds := authTransportCredentials("production")
	if tlsCreds.Info().SecurityProtocol == "insecure" {
		t.Fatal("production must use TLS")
	}
}
