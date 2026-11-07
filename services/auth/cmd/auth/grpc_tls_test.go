package main

import (
	"context"
	"crypto/tls"
	"net"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/infra/testing/tlscert"
	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"github.com/Rick1330/ibex-harness/services/auth/internal/config"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/credentials"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/status"
)

// TestUnit_GRPCTLSNegativeTransport is the ADR-0097 §4 negative transport test:
// a client without the per-install CA cannot complete the handshake, while a
// client holding the CA reaches the auth interceptor. It proves the real
// newAuthGRPCServer path serves TLS, not just that credentials were configured.
func TestUnit_GRPCTLSNegativeTransport(t *testing.T) {
	t.Parallel()

	pair := tlscert.Generate(t, t.TempDir(), tlscert.Options{})
	cfg := config.Config{
		Environment:     "production",
		GRPCTLSCertFile: pair.CertFile,
		GRPCTLSKeyFile:  pair.KeyFile,
	}

	db := openTestDB(t)
	reg := newTestAuthRegistry(t, db)
	deps := newTestAuthServiceDeps(t, db, reg)

	srv, err := newAuthGRPCServer(cfg, deps, reg)
	if err != nil {
		t.Fatalf("newAuthGRPCServer: %v", err)
	}
	lis, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listen: %v", err)
	}
	go func() { _ = srv.Serve(lis) }()
	t.Cleanup(func() {
		srv.Stop()
		_ = lis.Close()
	})

	t.Run("insecure client is rejected at the transport", func(t *testing.T) {
		conn := dialTestClient(t, lis.Addr().String(), insecure.NewCredentials())
		_, err := authv1.NewAuthServiceClient(conn).CreateToken(
			testCallContext(t), &authv1.CreateTokenRequest{})
		code := status.Code(err)
		if code != codes.Unavailable && code != codes.Internal {
			t.Fatalf("insecure client code = %s (err %v), want Unavailable/Internal transport failure", code, err)
		}
		if code == codes.Unauthenticated {
			t.Fatal("insecure client reached the auth interceptor; the server is not serving TLS")
		}
	})

	t.Run("client holding the CA reaches the interceptor", func(t *testing.T) {
		conn := dialTestClient(t, lis.Addr().String(), credentials.NewTLS(&tls.Config{
			RootCAs:    pair.CAPool,
			MinVersion: tls.VersionTLS12,
		}))
		_, err := authv1.NewAuthServiceClient(conn).CreateToken(
			testCallContext(t), &authv1.CreateTokenRequest{})
		code := status.Code(err)
		if code != codes.Unauthenticated && code != codes.PermissionDenied {
			t.Fatalf("CA client code = %s (err %v), want Unauthenticated/PermissionDenied from the interceptor", code, err)
		}
	})
}

// TestUnit_AuthGRPCServerTransportCredentials_RefusesNonDevelopmentWithoutPair
// proves the constructor defence does not depend on Config.Validate: a Config
// assembled by hand outside development with no certificate pair must be
// refused, never silently served as plaintext (ADR-0097 §4, fail closed).
func TestUnit_AuthGRPCServerTransportCredentials_RefusesNonDevelopmentWithoutPair(t *testing.T) {
	t.Parallel()
	for _, environment := range []string{"staging", "production"} {
		environment := environment
		t.Run(environment, func(t *testing.T) {
			t.Parallel()
			creds, err := authGRPCServerTransportCredentials(config.Config{Environment: environment})
			if err == nil {
				t.Fatalf("authGRPCServerTransportCredentials accepted %s without a pair (creds=%v)", environment, creds)
			}
			if creds != nil {
				t.Fatal("expected nil credentials when the pair is missing")
			}
		})
	}
}

// TestUnit_NewAuthGRPCServer_RefusesNonDevelopmentWithoutPair is the same
// negative at the constructor boundary: Validate() is deliberately skipped.
func TestUnit_NewAuthGRPCServer_RefusesNonDevelopmentWithoutPair(t *testing.T) {
	t.Parallel()
	db := openTestDB(t)
	reg := newTestAuthRegistry(t, db)
	deps := newTestAuthServiceDeps(t, db, reg)
	if _, err := newAuthGRPCServer(config.Config{Environment: "production"}, deps, reg); err == nil {
		t.Fatal("newAuthGRPCServer accepted production without a gRPC TLS pair")
	}
}

// TestUnit_AuthGRPCServerTransportCredentials_RejectsBadPair covers the
// load-error path: a configured but unreadable/garbage pair must fail the
// constructor, never fall back to plaintext.
func TestUnit_AuthGRPCServerTransportCredentials_RejectsBadPair(t *testing.T) {
	t.Parallel()
	dir := t.TempDir()
	certFile := filepath.Join(dir, "bad.crt")
	keyFile := filepath.Join(dir, "bad.key")
	if err := os.WriteFile(certFile, []byte("not a certificate"), 0o600); err != nil {
		t.Fatalf("write bad cert: %v", err)
	}
	if err := os.WriteFile(keyFile, []byte("not a key"), 0o600); err != nil {
		t.Fatalf("write bad key: %v", err)
	}
	if _, err := authGRPCServerTransportCredentials(config.Config{
		Environment:     "development",
		GRPCTLSCertFile: certFile,
		GRPCTLSKeyFile:  keyFile,
	}); err == nil {
		t.Fatal("authGRPCServerTransportCredentials accepted a garbage pair")
	}
}

func dialTestClient(t *testing.T, addr string, creds credentials.TransportCredentials) *grpc.ClientConn {
	t.Helper()
	conn, err := grpc.NewClient(addr, grpc.WithTransportCredentials(creds))
	if err != nil {
		t.Fatalf("grpc.NewClient: %v", err)
	}
	t.Cleanup(func() { _ = conn.Close() })
	return conn
}

func testCallContext(t *testing.T) context.Context {
	t.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	t.Cleanup(cancel)
	return ctx
}
