package healthcheck

import (
	"bufio"
	"context"
	"net"
	"testing"
)

func TestRedisPing_MissingURL(t *testing.T) {
	t.Parallel()
	err := RedisPing("")(context.Background())
	if err == nil || err.Error() != "missing REDIS_URL" {
		t.Fatalf("unexpected error: %v", err)
	}
}

func TestRedisPing_OK(t *testing.T) {
	t.Parallel()
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listen: %v", err)
	}
	defer func() { _ = listener.Close() }()

	done := make(chan struct{})
	go func() {
		defer close(done)
		conn, err := listener.Accept()
		if err != nil {
			return
		}
		defer func() { _ = conn.Close() }()
		reader := bufio.NewReader(conn)
		_, _ = reader.ReadString('\n')
		_, _ = reader.ReadString('\n')
		_, _ = reader.ReadString('\n')
		_, _ = conn.Write([]byte("+PONG\r\n"))
	}()

	err = RedisPing("redis://" + listener.Addr().String() + "/0")(context.Background())
	if err != nil {
		t.Fatalf("expected ready, got %v", err)
	}
	<-done
}
