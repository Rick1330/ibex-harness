package bootstrap

import (
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/infra/testing/grpctest"
	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/config"
)

func assertAuthClientsPresent(t *testing.T, b authClients) {
	t.Helper()
	if b.validator == nil {
		t.Fatal("validator nil")
	}
	if b.agentVerifier == nil {
		t.Fatal("agentVerifier nil")
	}
	if b.client == nil {
		t.Fatal("client nil")
	}
	if b.conn == nil {
		t.Fatal("conn nil")
	}
}

func assertAuthClientsAbsent(t *testing.T, b authClients) {
	t.Helper()
	if b.validator != nil {
		t.Fatal("validator should be nil")
	}
	if b.agentVerifier != nil {
		t.Fatal("agentVerifier should be nil")
	}
	if b.client != nil {
		t.Fatal("client should be nil")
	}
	if b.conn != nil {
		t.Fatal("conn should be nil")
	}
}

func TestSetupAuthClients_WithGRPCServer(t *testing.T) {
	lis := grpctest.StartUnimplementedAuthServer(t)
	log := logger.Discard("proxy")
	clients, err := setupAuthClients(config.Config{
		Environment: "development", AuthGRPCAddr: lis.Addr().String(), AuthValidateTimeout: time.Second,
	}, log, nil)
	if err != nil {
		t.Fatalf("setupAuthClients: %v", err)
	}
	t.Cleanup(func() { _ = clients.conn.Close() })
	assertAuthClientsPresent(t, clients)
}

func TestSetupAuthClients_WithAuthCacheEnabled(t *testing.T) {
	lis := grpctest.StartUnimplementedAuthServer(t)
	log := logger.Discard("proxy")
	cfg := config.Config{
		Environment:         "development",
		AuthGRPCAddr:        lis.Addr().String(),
		AuthValidateTimeout: time.Second,
		AuthCache: config.AuthCacheConfig{
			Enabled:            true,
			LRUCapacity:        100,
			LRUMaxTTL:          30 * time.Second,
			BloomExpectedItems: 1000,
			BloomFPRate:        0.001,
		},
	}
	clients, err := setupAuthClients(cfg, log, nil)
	if err != nil {
		t.Fatalf("setupAuthClients: %v", err)
	}
	t.Cleanup(func() { _ = clients.conn.Close() })
	assertAuthClientsPresent(t, clients)
	if _, ok := clients.validator.(auth.CacheInvalidator); !ok {
		t.Fatal("expected caching validator implementing CacheInvalidator")
	}
}

func TestSetupAuthClients_EmptyAddr(t *testing.T) {
	log := logger.Discard("proxy")
	clients, err := setupAuthClients(config.Config{AuthGRPCAddr: ""}, log, nil)
	if err != nil {
		t.Fatalf("setupAuthClients: %v", err)
	}
	assertAuthClientsAbsent(t, clients)
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
