package main

import (
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/infra/testing/grpctest"
	"github.com/Rick1330/ibex-harness/packages/logger"
	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/config"
	"google.golang.org/grpc"
)

type authClientBundle struct {
	validator     auth.TokenValidator
	agentVerifier auth.AgentVerifier
	client        authv1.AuthServiceClient
	conn          *grpc.ClientConn
}

func assertAuthClientsPresent(t *testing.T, b authClientBundle) {
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

func assertAuthClientsAbsent(t *testing.T, b authClientBundle) {
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
	validator, agentVerifier, client, conn, err := setupAuthClients(config.Config{
		AuthGRPCAddr: lis.Addr().String(), AuthValidateTimeout: time.Second,
	}, log, nil)
	if err != nil {
		t.Fatalf("setupAuthClients: %v", err)
	}
	t.Cleanup(func() { _ = conn.Close() })
	assertAuthClientsPresent(t, authClientBundle{validator, agentVerifier, client, conn})
}

func TestSetupAuthClients_WithAuthCacheEnabled(t *testing.T) {
	lis := grpctest.StartUnimplementedAuthServer(t)
	log := logger.Discard("proxy")
	cfg := config.Config{
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
	validator, agentVerifier, client, conn, err := setupAuthClients(cfg, log, nil)
	if err != nil {
		t.Fatalf("setupAuthClients: %v", err)
	}
	t.Cleanup(func() { _ = conn.Close() })
	assertAuthClientsPresent(t, authClientBundle{validator, agentVerifier, client, conn})
	if _, ok := validator.(auth.CacheInvalidator); !ok {
		t.Fatal("expected caching validator implementing CacheInvalidator")
	}
}

func TestSetupAuthClients_EmptyAddr(t *testing.T) {
	log := logger.Discard("proxy")
	validator, agentVerifier, client, conn, err := setupAuthClients(config.Config{AuthGRPCAddr: ""}, log, nil)
	if err != nil {
		t.Fatalf("setupAuthClients: %v", err)
	}
	assertAuthClientsAbsent(t, authClientBundle{validator, agentVerifier, client, conn})
}
