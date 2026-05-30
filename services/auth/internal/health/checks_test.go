package health

import (
	"context"
	"net"
	"testing"
)

func TestReadyPostgresMissingDSN(t *testing.T) {
	result := ReadyPostgres(context.Background(), "")
	if result.OK {
		t.Fatal("expected missing DSN to be not ready")
	}
	if result.Reason != "missing POSTGRES_DSN" {
		t.Fatalf("unexpected reason: %s", result.Reason)
	}
}

func TestReadyPostgresTCPReachable(t *testing.T) {
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listen: %v", err)
	}
	defer listener.Close()

	done := make(chan struct{})
	go func() {
		conn, err := listener.Accept()
		if err == nil {
			_ = conn.Close()
		}
		close(done)
	}()

	result := ReadyPostgres(context.Background(), "postgres://user:pass@"+listener.Addr().String()+"/ibex")
	if !result.OK {
		t.Fatalf("expected ready, got reason %q", result.Reason)
	}
	<-done
}
