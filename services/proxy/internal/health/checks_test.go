package health

import (
	"bufio"
	"context"
	"net"
	"testing"
)

func TestReadyRedisMissingURL(t *testing.T) {
	result := ReadyRedis(context.Background(), "")
	if result.OK {
		t.Fatal("expected missing URL to be not ready")
	}
	if result.Reason != "missing REDIS_URL" {
		t.Fatalf("unexpected reason: %s", result.Reason)
	}
}

func TestReadyRedisPing(t *testing.T) {
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listen: %v", err)
	}
	defer listener.Close()

	done := make(chan struct{})
	go func() {
		defer close(done)
		conn, err := listener.Accept()
		if err != nil {
			return
		}
		defer conn.Close()
		reader := bufio.NewReader(conn)
		_, _ = reader.ReadString('\n')
		_, _ = reader.ReadString('\n')
		_, _ = reader.ReadString('\n')
		_, _ = conn.Write([]byte("+PONG\r\n"))
	}()

	result := ReadyRedis(context.Background(), "redis://"+listener.Addr().String()+"/0")
	if !result.OK {
		t.Fatalf("expected ready, got reason %q", result.Reason)
	}
	<-done
}
