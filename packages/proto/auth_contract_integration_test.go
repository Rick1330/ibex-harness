//go:build integration

package proto_test

import (
	"context"
	"fmt"
	"net"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"testing"

	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/status"
	"google.golang.org/grpc/test/bufconn"
)

const grpcBufSize = 1024 * 1024

func protoModuleDir() string {
	_, filename, _, _ := runtime.Caller(1)
	return filepath.Dir(filename)
}

func TestMain(m *testing.M) {
	if _, err := exec.LookPath("buf"); err != nil {
		fmt.Fprintf(os.Stderr, "integration: buf not on PATH; generated stub tests will skip\n")
		os.Exit(m.Run())
	}

	dir := protoModuleDir()
	cmd := exec.Command("buf", "generate")
	cmd.Dir = dir
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	if err := cmd.Run(); err != nil {
		fmt.Fprintf(os.Stderr, "integration: buf generate failed: %v\n", err)
		os.Exit(1)
	}

	os.Exit(m.Run())
}

func generatedAuthDir(t *testing.T) string {
	t.Helper()
	return filepath.Join(protoModuleDir(), "gen", "go", "ibex", "auth", "v1")
}

func TestGeneratedAuthFilesExist(t *testing.T) {
	dir := generatedAuthDir(t)
	for _, name := range []string{"auth.pb.go", "auth_grpc.pb.go"} {
		path := filepath.Join(dir, name)
		if _, err := os.Stat(path); err != nil {
			t.Fatalf("missing generated file %s: %v", path, err)
		}
	}
}

type unimplementedAuthServer struct {
	authv1.UnimplementedAuthServiceServer
}

func TestAuthValidateTokenGRPCSmoke(t *testing.T) {
	lis := bufconn.Listen(grpcBufSize)
	srv := grpc.NewServer()
	authv1.RegisterAuthServiceServer(srv, &unimplementedAuthServer{})
	go func() {
		if err := srv.Serve(lis); err != nil {
			// Serve returns when stopped; ignore after test.
		}
	}()
	t.Cleanup(func() { srv.Stop() })

	conn, err := grpc.NewClient("passthrough:///bufnet",
		grpc.WithContextDialer(func(ctx context.Context, _ string) (net.Conn, error) {
			return lis.DialContext(ctx)
		}),
		grpc.WithTransportCredentials(insecure.NewCredentials()),
	)
	if err != nil {
		t.Fatalf("dial: %v", err)
	}
	t.Cleanup(func() { _ = conn.Close() })

	client := authv1.NewAuthServiceClient(conn)
	ctx := context.Background()
	_, err = client.ValidateToken(ctx, &authv1.ValidateTokenRequest{AccessToken: "ibex_pat_test"})
	if err == nil {
		t.Fatal("expected gRPC error from UnimplementedAuthServiceServer")
	}
	st, ok := status.FromError(err)
	if !ok {
		t.Fatalf("not a gRPC status error: %v", err)
	}
	if st.Code() != codes.Unimplemented {
		t.Fatalf("status code: got %v want Unimplemented", st.Code())
	}
}
