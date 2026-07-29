package bootstrap

import (
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/infra/testing/grpctest"
	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/config"
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

func TestSetupAuthClients_success(t *testing.T) {
	t.Parallel()

	cases := []struct {
		name       string
		authCache  config.AuthCacheConfig
		checkCache bool
	}{
		{name: "grpc only"},
		{
			name: "auth cache",
			authCache: config.AuthCacheConfig{
				Enabled:            true,
				LRUCapacity:        100,
				LRUMaxTTL:          30 * time.Second,
				BloomExpectedItems: 1000,
				BloomFPRate:        0.001,
			},
			checkCache: true,
		},
	}

	for _, tc := range cases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			lis := grpctest.StartUnimplementedAuthServer(t)
			log := logger.Discard("proxy")
			cfg := config.Config{
				Environment:         "development",
				AuthGRPCAddr:        lis.Addr().String(),
				AuthValidateTimeout: time.Second,
				AuthCache:           tc.authCache,
			}
			clients, err := setupAuthClients(cfg, log, nil)
			if err != nil {
				t.Fatalf("setupAuthClients: %v", err)
			}
			t.Cleanup(func() {
				if err := clients.conn.Close(); err != nil {
					t.Errorf("close conn: %v", err)
				}
			})
			assertAuthClients(t, clients, true)
			if tc.checkCache {
				if _, ok := clients.validator.(auth.CacheInvalidator); !ok {
					t.Fatal("expected caching validator implementing CacheInvalidator")
				}
			}
		})
	}
}

func TestSetupAuthClients_EmptyAddr(t *testing.T) {
	t.Parallel()
	log := logger.Discard("proxy")
	clients, err := setupAuthClients(config.Config{AuthGRPCAddr: ""}, log, nil)
	if err != nil {
		t.Fatalf("setupAuthClients: %v", err)
	}
	assertAuthClients(t, clients, false)
}

func TestSetupAuthClients_InvalidAuthCacheConfig(t *testing.T) {
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
	}, log, nil)
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
