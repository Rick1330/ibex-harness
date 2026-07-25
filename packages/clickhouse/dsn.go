package clickhouse

import (
	"fmt"
	"net"
	"net/url"
	"strings"

	"github.com/ClickHouse/clickhouse-go/v2"
)

// parseOptions builds clickhouse-go Options from an app CLICKHOUSE_DSN.
// HTTP (8123) is the app protocol per ADR-0033; native is migrate-only.
func parseOptions(dsn string) (*clickhouse.Options, error) {
	dsn = strings.TrimSpace(dsn)
	if dsn == "" {
		return nil, fmt.Errorf("clickhouse: empty DSN")
	}
	opts, err := clickhouse.ParseDSN(dsn)
	if err != nil {
		return nil, fmt.Errorf("clickhouse: parse DSN: %w", err)
	}
	if opts.Auth.Database == "" {
		opts.Auth.Database = "ibex"
	}
	if shouldUseHTTP(opts) {
		opts.Protocol = clickhouse.HTTP
	}
	return opts, nil
}

func shouldUseHTTP(opts *clickhouse.Options) bool {
	if opts.Protocol == clickhouse.HTTP {
		return true
	}
	for _, addr := range opts.Addr {
		if httpAppPort(addr) {
			return true
		}
	}
	return false
}

func httpAppPort(addr string) bool {
	_, port, err := net.SplitHostPort(addr)
	if err != nil {
		// Bare host without port — not an HTTP app endpoint we remap.
		return false
	}
	switch port {
	case "8123", "8124", "8443":
		return true
	default:
		return false
	}
}

// RedactedDSN returns a DSN safe for logging (password stripped from userinfo and query).
func RedactedDSN(dsn string) string {
	u, err := url.Parse(dsn)
	if err != nil || u.Scheme == "" {
		return "(invalid dsn)"
	}
	if u.User != nil {
		u.User = url.User(u.User.Username())
	}
	q := u.Query()
	for _, key := range []string{"password", "passwd"} {
		if q.Has(key) {
			q.Del(key)
		}
	}
	u.RawQuery = q.Encode()
	return u.String()
}
