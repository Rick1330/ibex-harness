package bootstrap

import (
	"crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"encoding/json"
	"encoding/pem"
	"strings"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/infra/testing/grpctest"
	"github.com/Rick1330/ibex-harness/packages/logger"
	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/config"
)

// stubAuthServiceClient satisfies authv1.AuthServiceClient for wiring tests;
// the policy snapshot client only checks for a non-nil implementation.
type stubAuthServiceClient struct {
	authv1.AuthServiceClient
}

func testPolicyKeysJSON(t *testing.T) string {
	t.Helper()
	key, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatal(err)
	}
	der, err := x509.MarshalPKIXPublicKey(&key.PublicKey)
	if err != nil {
		t.Fatal(err)
	}
	pubPEM := string(pem.EncodeToMemory(&pem.Block{Type: "PUBLIC KEY", Bytes: der}))
	raw, err := json.Marshal(map[string]string{"v1": pubPEM})
	if err != nil {
		t.Fatal(err)
	}
	return string(raw)
}

func TestUnit_SetupPolicySnapshot(t *testing.T) {
	t.Parallel()
	log := logger.Discard("proxy")
	validKeys := testPolicyKeysJSON(t)

	t.Run("stage off without keys", func(t *testing.T) {
		fetcher, verifier, err := setupPolicySnapshot(config.Config{}, log, nil)
		if err != nil {
			t.Fatalf("setupPolicySnapshot: %v", err)
		}
		if fetcher != nil || verifier != nil {
			t.Fatalf("fetcher=%v verifier=%v want both nil", fetcher, verifier)
		}
	})

	t.Run("configured with valid keys", func(t *testing.T) {
		fetcher, verifier, err := setupPolicySnapshot(config.Config{
			PolicyPublicKeysJSON: validKeys, PolicyMinEpoch: 2, AuthValidateTimeout: time.Second,
		}, log, &stubAuthServiceClient{})
		if err != nil {
			t.Fatalf("setupPolicySnapshot: %v", err)
		}
		if _, ok := fetcher.(*auth.GRPCPolicySnapshotClient); !ok {
			t.Fatalf("fetcher type = %T", fetcher)
		}
		if verifier == nil {
			t.Fatal("verifier is nil")
		}
	})

	t.Run("rejects invalid keys json", func(t *testing.T) {
		_, _, err := setupPolicySnapshot(config.Config{PolicyPublicKeysJSON: "{"}, log, &stubAuthServiceClient{})
		if err == nil || !strings.Contains(err.Error(), "policy snapshot keys") {
			t.Fatalf("err = %v", err)
		}
	})

	t.Run("rejects invalid key pem", func(t *testing.T) {
		raw, err := json.Marshal(map[string]string{"v1": "not-a-pem"})
		if err != nil {
			t.Fatal(err)
		}
		_, _, err = setupPolicySnapshot(config.Config{PolicyPublicKeysJSON: string(raw)}, log, &stubAuthServiceClient{})
		if err == nil || !strings.Contains(err.Error(), "policy snapshot keys") {
			t.Fatalf("err = %v", err)
		}
	})

	t.Run("rejects negative min epoch", func(t *testing.T) {
		_, _, err := setupPolicySnapshot(config.Config{
			PolicyPublicKeysJSON: validKeys, PolicyMinEpoch: -1,
		}, log, &stubAuthServiceClient{})
		if err == nil || !strings.Contains(err.Error(), "policy snapshot verifier") {
			t.Fatalf("err = %v", err)
		}
	})

	t.Run("rejects nil auth client", func(t *testing.T) {
		_, _, err := setupPolicySnapshot(config.Config{PolicyPublicKeysJSON: validKeys}, log, nil)
		if err == nil || !strings.Contains(err.Error(), "policy snapshot client") {
			t.Fatalf("err = %v", err)
		}
	})
}

func TestUnit_SetupAuthClients_WithPolicySnapshot(t *testing.T) {
	t.Parallel()
	lis := grpctest.StartUnimplementedAuthServer(t)
	cfg := config.Config{
		Environment:          "development",
		AuthGRPCAddr:         lis.Addr().String(),
		AuthValidateTimeout:  time.Second,
		PolicyPublicKeysJSON: testPolicyKeysJSON(t),
		PolicyMinEpoch:       1,
	}
	clients, err := setupAuthClients(cfg, logger.Discard("proxy"), nil, nil)
	if err != nil {
		t.Fatalf("setupAuthClients: %v", err)
	}
	t.Cleanup(func() {
		if err := clients.conn.Close(); err != nil {
			t.Errorf("close conn: %v", err)
		}
	})
	if clients.policyFetcher == nil || clients.policyVerifier == nil {
		t.Fatalf("policy stage not wired: fetcher=%v verifier=%v", clients.policyFetcher, clients.policyVerifier)
	}
}

func TestUnit_SetupAuthClients_PolicySnapshotConfigError(t *testing.T) {
	t.Parallel()
	lis := grpctest.StartUnimplementedAuthServer(t)
	cfg := config.Config{
		Environment:          "development",
		AuthGRPCAddr:         lis.Addr().String(),
		AuthValidateTimeout:  time.Second,
		PolicyPublicKeysJSON: testPolicyKeysJSON(t),
		PolicyMinEpoch:       -1,
	}
	_, err := setupAuthClients(cfg, logger.Discard("proxy"), nil, nil)
	if err == nil || !strings.Contains(err.Error(), "policy snapshot verifier") {
		t.Fatalf("err = %v", err)
	}
}
