package bootstrap

import (
	"net"
	"os"
	"syscall"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/infra/testing/grpctest"
	"github.com/alicebob/miniredis/v2"
)

func proxyBootstrapSmokeEnv(t *testing.T) (sigCh chan os.Signal, httpPort string) {
	t.Helper()
	mr := miniredis.RunT(t)
	lis := grpctest.StartUnimplementedAuthServer(t)

	httpLis, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	_, portStr, err := net.SplitHostPort(httpLis.Addr().String())
	if err != nil {
		t.Fatal(err)
	}
	_ = httpLis.Close()

	t.Setenv("IBEX_ENV", "development")
	t.Setenv("REDIS_URL", "redis://"+mr.Addr()+"/0")
	t.Setenv("IBEX_AUTH_GRPC_ADDR", lis.Addr().String())
	t.Setenv("IBEX_PORT", portStr)

	return make(chan os.Signal, 1), portStr
}

func waitForTCP(t *testing.T, addr string) {
	t.Helper()
	deadline := time.Now().Add(2 * time.Second)
	for time.Now().Before(deadline) {
		conn, err := net.DialTimeout("tcp", addr, 50*time.Millisecond)
		if err == nil {
			_ = conn.Close()
			return
		}
	}
	t.Fatalf("timeout waiting for %s", addr)
}

func TestRun_StopsOnSignal(t *testing.T) {
	sigCh, portStr := proxyBootstrapSmokeEnv(t)
	done := make(chan int, 1)
	go func() { done <- runBootstrap(nil, sigCh) }()
	waitForTCP(t, net.JoinHostPort("127.0.0.1", portStr))
	sigCh <- syscall.SIGTERM
	select {
	case code := <-done:
		if code != 0 {
			t.Fatalf("runBootstrap() = %d, want 0", code)
		}
	case <-time.After(5 * time.Second):
		t.Fatal("timed out waiting for shutdown")
	}
}
