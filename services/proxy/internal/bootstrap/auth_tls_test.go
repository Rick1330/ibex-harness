package bootstrap

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
	"github.com/Rick1330/ibex-harness/services/proxy/internal/config"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/credentials"
	"google.golang.org/grpc/status"
)

// TestUnit_AuthTransportCredentials pins the ADR-0097 §4 client rule: a
// configured per-install CA selects TLS in every environment (including
// development), no CA stays plaintext only in development, and a bad CA file
// fails startup instead of every ValidateToken call.
func TestUnit_AuthTransportCredentials(t *testing.T) {
	t.Parallel()

	validPair := tlscert.Generate(t, t.TempDir(), tlscert.Options{})
	missing := filepath.Join(t.TempDir(), "missing-ca.pem")
	garbage := filepath.Join(t.TempDir(), "garbage-ca.pem")
	if err := os.WriteFile(garbage, []byte("not a pem certificate"), 0o644); err != nil {
		t.Fatalf("write garbage CA: %v", err)
	}
	directory := t.TempDir()

	tests := []struct {
		name        string
		environment string
		caFile      string
		wantProto   string
		wantErr     bool
	}{
		{name: "development without CA is insecure", environment: "development", wantProto: "insecure"},
		{name: "empty environment without CA is TLS", environment: "", wantProto: "tls"},
		{name: "production without CA is TLS", environment: "production", wantProto: "tls"},
		{name: "staging without CA is TLS", environment: "staging", wantProto: "tls"},
		{name: "development with custom CA is TLS", environment: "development", caFile: validPair.CAFile, wantProto: "tls"},
		{name: "production with custom CA is TLS", environment: "production", caFile: validPair.CAFile, wantProto: "tls"},
		{name: "missing CA file is an error", environment: "development", caFile: missing, wantErr: true},
		{name: "directory CA path is an error", environment: "development", caFile: directory, wantErr: true},
		{name: "garbage CA file is an error", environment: "development", caFile: garbage, wantErr: true},
	}
	for _, tc := range tests {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			creds, err := authTransportCredentials(tc.environment, tc.caFile)
			if tc.wantErr {
				if err == nil {
					t.Fatal("expected an error")
				}
				return
			}
			if err != nil {
				t.Fatalf("authTransportCredentials: %v", err)
			}
			if got := creds.Info().SecurityProtocol; got != tc.wantProto {
				t.Fatalf("SecurityProtocol=%q, want %q", got, tc.wantProto)
			}
		})
	}
}

// TestUnit_ContextTransportCredentials_IgnoresAuthCA proves the context hop
// never borrows the AuthService CA: co-located production stays plaintext even
// when a CA is configured, and a non-co-located hop keeps the TLS decision.
func TestUnit_ContextTransportCredentials_IgnoresAuthCA(t *testing.T) {
	t.Parallel()

	pair := tlscert.Generate(t, t.TempDir(), tlscert.Options{})
	cases := []struct {
		name      string
		colocated bool
		wantProto string
	}{
		{name: "colocated production stays plaintext", colocated: true, wantProto: "insecure"},
		{name: "non-colocated production is TLS", colocated: false, wantProto: "tls"},
	}
	for _, tc := range cases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			cfg := config.Config{
				Environment:        "production",
				ContextColocated:   tc.colocated,
				AuthGRPCCACertFile: pair.CAFile,
			}
			creds, err := contextTransportCredentials(cfg)
			if err != nil {
				t.Fatalf("contextTransportCredentials: %v", err)
			}
			if got := creds.Info().SecurityProtocol; got != tc.wantProto {
				t.Fatalf("SecurityProtocol=%q, want %q", got, tc.wantProto)
			}
		})
	}
}

// TestUnit_DialAuthGRPC_RejectsBadCA covers the startup wrapper: a configured
// CA that cannot be loaded must fail the dial construction, not every request.
func TestUnit_DialAuthGRPC_RejectsBadCA(t *testing.T) {
	t.Parallel()
	cfg := config.Config{
		Environment:        "development",
		AuthGRPCAddr:       "127.0.0.1:1",
		AuthGRPCCACertFile: filepath.Join(t.TempDir(), "missing.pem"),
	}
	if _, err := dialAuthGRPC(cfg); err == nil {
		t.Fatal("dialAuthGRPC accepted a missing CA file")
	}
}

// TestUnit_AuthTransportCredentials_Handshake is the hermetic handshake
// negative: a client holding the server CA reaches the gRPC service, while a
// client holding a different CA fails at the TLS handshake.
func TestUnit_AuthTransportCredentials_Handshake(t *testing.T) {
	t.Parallel()

	serverPair := tlscert.Generate(t, t.TempDir(), tlscert.Options{})
	otherPair := tlscert.Generate(t, t.TempDir(), tlscert.Options{})
	addr, stop := startTLSAuthStub(t, serverPair)
	t.Cleanup(stop)

	t.Run("client with matching CA reaches the service", func(t *testing.T) {
		conn := dialAuthStub(t, addr, serverPair.CAFile)
		_, err := authv1.NewAuthServiceClient(conn).ValidateToken(
			callContext(t), &authv1.ValidateTokenRequest{})
		if code := status.Code(err); code != codes.Unimplemented {
			t.Fatalf("matching CA code = %s (err %v), want Unimplemented from the server", code, err)
		}
	})

	t.Run("client with a different CA fails the handshake", func(t *testing.T) {
		conn := dialAuthStub(t, addr, otherPair.CAFile)
		_, err := authv1.NewAuthServiceClient(conn).ValidateToken(
			callContext(t), &authv1.ValidateTokenRequest{})
		if code := status.Code(err); code != codes.Unavailable {
			t.Fatalf("different CA code = %s (err %v), want Unavailable transport failure", code, err)
		}
	})
}

func startTLSAuthStub(t *testing.T, pair tlscert.Pair) (string, func()) {
	t.Helper()
	cert, err := tls.LoadX509KeyPair(pair.CertFile, pair.KeyFile)
	if err != nil {
		t.Fatalf("load server pair: %v", err)
	}
	srv := grpc.NewServer(grpc.Creds(credentials.NewTLS(&tls.Config{
		Certificates: []tls.Certificate{cert},
		MinVersion:   tls.VersionTLS12,
	})))
	authv1.RegisterAuthServiceServer(srv, authv1.UnimplementedAuthServiceServer{})
	lis, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listen: %v", err)
	}
	go func() { _ = srv.Serve(lis) }()
	return lis.Addr().String(), func() {
		srv.Stop()
		_ = lis.Close()
	}
}

func dialAuthStub(t *testing.T, addr, caFile string) *grpc.ClientConn {
	t.Helper()
	creds, err := authTransportCredentials("production", caFile)
	if err != nil {
		t.Fatalf("authTransportCredentials: %v", err)
	}
	conn, err := grpc.NewClient(addr, grpc.WithTransportCredentials(creds))
	if err != nil {
		t.Fatalf("grpc.NewClient: %v", err)
	}
	t.Cleanup(func() { _ = conn.Close() })
	return conn
}

func callContext(t *testing.T) context.Context {
	t.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	t.Cleanup(cancel)
	return ctx
}
