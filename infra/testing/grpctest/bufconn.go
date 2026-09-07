package grpctest

import (
	"context"
	"net"
	"testing"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/test/bufconn"
)

// StartInsecureBufconn spins up an in-memory gRPC server, runs register to attach
// services, and returns a client conn dialed over bufconn. Loopback-only test
// fixture; production uses TLS/mTLS.
func StartInsecureBufconn(t *testing.T, register func(*grpc.Server)) *grpc.ClientConn {
	t.Helper()
	lis := bufconn.Listen(1 << 20)
	server := grpc.NewServer(grpc.Creds(insecure.NewCredentials()))
	register(server)
	go serveBufListener(server, lis)
	t.Cleanup(server.Stop)

	conn, err := grpc.NewClient(
		"passthrough:///grpctest-bufconn",
		grpc.WithContextDialer(bufDialer(lis)),
		grpc.WithTransportCredentials(insecure.NewCredentials()),
	)
	if err != nil {
		t.Fatalf("grpctest bufconn dial: %v", err)
	}
	t.Cleanup(func() { _ = conn.Close() })
	return conn
}

func serveBufListener(server *grpc.Server, lis *bufconn.Listener) {
	_ = server.Serve(lis) //nolint:errcheck // stopped via t.Cleanup
}

func bufDialer(lis *bufconn.Listener) func(context.Context, string) (net.Conn, error) {
	return func(ctx context.Context, _ string) (net.Conn, error) {
		return lis.DialContext(ctx)
	}
}
