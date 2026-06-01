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

func TestRedisEndpointNoUserInfo(t *testing.T) {
	ep, err := redisEndpoint("redis://localhost:6379/0")
	if err != nil {
		t.Fatalf("redisEndpoint: %v", err)
	}
	if ep.address != "localhost:6379" {
		t.Fatalf("unexpected address: %s", ep.address)
	}
	if ep.password != "" || ep.username != "" {
		t.Fatalf("expected empty credentials, got user=%q pass=%q", ep.username, ep.password)
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
