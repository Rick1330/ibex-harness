package health

import (
	"bufio"
	"context"
	"fmt"
	"net"
	"net/url"
	"strings"
	"time"
)

type Result struct {
	OK     bool
	Reason string
}

func ReadyRedis(ctx context.Context, rawURL string) Result {
	if rawURL == "" {
		return Result{OK: false, Reason: "missing REDIS_URL"}
	}

	endpoint, err := redisEndpoint(rawURL)
	if err != nil {
		return Result{OK: false, Reason: "invalid REDIS_URL"}
	}

	dialer := net.Dialer{Timeout: 500 * time.Millisecond}
	conn, err := dialer.DialContext(ctx, "tcp", endpoint.address)
	if err != nil {
		if ctx.Err() != nil {
			return Result{OK: false, Reason: "redis readiness check timed out"}
		}
		return Result{OK: false, Reason: "redis unreachable"}
	}
	defer func() { _ = conn.Close() }()

	deadline := time.Now().Add(500 * time.Millisecond)
	_ = conn.SetDeadline(deadline)

	reader := bufio.NewReader(conn)
	if endpoint.password != "" {
		if err := writeRESP(conn, "AUTH", endpoint.authArgs()...); err != nil {
			return Result{OK: false, Reason: "redis auth failed"}
		}
		line, err := reader.ReadString('\n')
		if err != nil || !strings.HasPrefix(line, "+OK") {
			return Result{OK: false, Reason: "redis auth failed"}
		}
	}

	if err := writeRESP(conn, "PING"); err != nil {
		return Result{OK: false, Reason: "redis ping failed"}
	}
	line, err := reader.ReadString('\n')
	if err != nil {
		return Result{OK: false, Reason: "redis ping failed"}
	}
	if !strings.HasPrefix(line, "+PONG") {
		return Result{OK: false, Reason: "redis ping failed"}
	}
	return Result{OK: true}
}

type endpoint struct {
	address  string
	username string
	password string
}

func (e endpoint) authArgs() []string {
	if e.username == "" {
		return []string{e.password}
	}
	return []string{e.username, e.password}
}

func redisEndpoint(rawURL string) (endpoint, error) {
	parsed, err := url.Parse(rawURL)
	if err != nil {
		return endpoint{}, err
	}
	if parsed.Scheme != "redis" {
		return endpoint{}, fmt.Errorf("unsupported scheme")
	}
	if parsed.Hostname() == "" {
		return endpoint{}, fmt.Errorf("missing host")
	}
	port := parsed.Port()
	if port == "" {
		port = "6379"
	}
	var username, password string
	if parsed.User != nil {
		password, _ = parsed.User.Password()
		username = parsed.User.Username()
	}
	return endpoint{
		address:  net.JoinHostPort(parsed.Hostname(), port),
		username: username,
		password: password,
	}, nil
}

func writeRESP(conn net.Conn, command string, args ...string) error {
	parts := append([]string{command}, args...)
	if _, err := fmt.Fprintf(conn, "*%d\r\n", len(parts)); err != nil {
		return err
	}
	for _, part := range parts {
		if _, err := fmt.Fprintf(conn, "$%d\r\n%s\r\n", len(part), part); err != nil {
			return err
		}
	}
	return nil
}
