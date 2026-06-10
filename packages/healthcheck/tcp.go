package healthcheck

import (
	"context"
	"errors"
	"fmt"
	"net"
	"strings"
	"time"
)

// TCPReachable dials hostPort to verify a listener accepts connections.
func TCPReachable(hostPort string) Checker {
	return func(ctx context.Context) error {
		addr := strings.TrimSpace(hostPort)
		if addr == "" {
			return errors.New("tcp address not configured")
		}
		dialer := net.Dialer{Timeout: 500 * time.Millisecond}
		conn, err := dialer.DialContext(ctx, "tcp", addr)
		if err != nil {
			if ctx.Err() != nil {
				return errors.New("tcp readiness check timed out")
			}
			return fmt.Errorf("tcp unreachable: %w", err)
		}
		_ = conn.Close()
		return nil
	}
}
