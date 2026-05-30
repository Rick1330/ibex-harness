package health

import (
	"context"
	"errors"
	"fmt"
	"net"
	"net/url"
	"time"
)

type Result struct {
	OK     bool
	Reason string
}

func ReadyPostgres(ctx context.Context, dsn string) Result {
	if dsn == "" {
		return Result{OK: false, Reason: "missing POSTGRES_DSN"}
	}

	hostPort, err := postgresHostPort(dsn)
	if err != nil {
		return Result{OK: false, Reason: "invalid POSTGRES_DSN"}
	}

	dialer := net.Dialer{Timeout: 500 * time.Millisecond}
	conn, err := dialer.DialContext(ctx, "tcp", hostPort)
	if err != nil {
		if errors.Is(ctx.Err(), context.DeadlineExceeded) {
			return Result{OK: false, Reason: "postgres readiness check timed out"}
		}
		return Result{OK: false, Reason: "postgres unreachable"}
	}
	_ = conn.Close()
	return Result{OK: true}
}

func postgresHostPort(dsn string) (string, error) {
	parsed, err := url.Parse(dsn)
	if err != nil {
		return "", err
	}
	if parsed.Hostname() == "" {
		return "", fmt.Errorf("missing host")
	}
	port := parsed.Port()
	if port == "" {
		port = "5432"
	}
	return net.JoinHostPort(parsed.Hostname(), port), nil
}
