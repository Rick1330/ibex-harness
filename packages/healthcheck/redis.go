package healthcheck

import (
	"bufio"
	"context"
	"errors"
	"fmt"
	"net"
	"net/url"
	"strings"
	"time"
)

// RedisPing returns a checker that issues Redis PING over RESP.
func RedisPing(rawURL string) Checker {
	return func(ctx context.Context) error {
		return pingRedis(ctx, rawURL)
	}
}

func pingRedis(ctx context.Context, rawURL string) error {
	if strings.TrimSpace(rawURL) == "" {
		return errors.New("missing REDIS_URL")
	}

	endpoint, err := redisEndpoint(rawURL)
	if err != nil {
		return errors.New("invalid REDIS_URL")
	}

	conn, err := dialRedis(ctx, endpoint.address)
	if err != nil {
		return err
	}
	defer func() { _ = conn.Close() }()

	return redisPING(conn, endpoint)
}

func dialRedis(ctx context.Context, address string) (net.Conn, error) {
	dialer := net.Dialer{Timeout: 500 * time.Millisecond}
	conn, err := dialer.DialContext(ctx, "tcp", address)
	if err != nil {
		if ctx.Err() != nil {
			return nil, errors.New("redis readiness check timed out")
		}
		return nil, errors.New("redis unreachable")
	}
	deadline := time.Now().Add(500 * time.Millisecond)
	_ = conn.SetDeadline(deadline)
	return conn, nil
}

func redisPING(conn net.Conn, endpoint redisEndpointInfo) error {
	reader := bufio.NewReader(conn)
	if endpoint.password != "" {
		if err := writeRESP(conn, "AUTH", endpoint.authArgs()...); err != nil {
			return errors.New("redis auth failed")
		}
		line, err := reader.ReadString('\n')
		if err != nil || !strings.HasPrefix(line, "+OK") {
			return errors.New("redis auth failed")
		}
	}

	if err := writeRESP(conn, "PING"); err != nil {
		return errors.New("redis ping failed")
	}
	line, err := reader.ReadString('\n')
	if err != nil {
		return errors.New("redis ping failed")
	}
	if !strings.HasPrefix(line, "+PONG") {
		return errors.New("redis ping failed")
	}
	return nil
}

type redisEndpointInfo struct {
	address  string
	username string
	password string
}

func (e redisEndpointInfo) authArgs() []string {
	if e.username == "" {
		return []string{e.password}
	}
	return []string{e.username, e.password}
}

func redisEndpoint(rawURL string) (redisEndpointInfo, error) {
	parsed, err := url.Parse(rawURL)
	if err != nil {
		return redisEndpointInfo{}, err
	}
	if parsed.Scheme != "redis" {
		return redisEndpointInfo{}, fmt.Errorf("unsupported scheme")
	}
	if parsed.Hostname() == "" {
		return redisEndpointInfo{}, fmt.Errorf("missing host")
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
	return redisEndpointInfo{
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
