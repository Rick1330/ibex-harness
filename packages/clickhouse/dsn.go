package clickhouse

import (
	"fmt"
	"net"
	"net/url"
	"strings"

	"github.com/ClickHouse/clickhouse-go/v2"
	"github.com/Rick1330/ibex-harness/packages/chdsn"
)

func normalizeAppDSN(dsn string) string {
	u, err := url.Parse(dsn)
	if err != nil || u.Scheme == "" {
		return dsn
	}
	chdsn.FlattenUserinfoToQuery(u)
	// clickhouse-go HTTP mode POSTs using the DSN scheme; "clickhouse://" is
	// rejected by net/http. Rewrite app HTTP ports to http(s) before ParseDSN.
	rewriteHTTPScheme(u)
	return u.String()
}

func rewriteHTTPScheme(u *url.URL) {
	hostport := u.Host
	if hostport == "" {
		return
	}
	_, port, err := net.SplitHostPort(hostport)
	if err != nil {
		return
	}
	// App HTTP ports (ADR-0033). Do not rewrite :8443 to https — clickhouse-go
	// requires explicit TLS config for https DSNs ("https without TLS").
	switch port {
	case "8123", "8124":
		if u.Scheme == "clickhouse" || u.Scheme == "tcp" {
			u.Scheme = "http"
		}
	}
}

// parseOptions builds clickhouse-go Options from an app CLICKHOUSE_DSN.
// HTTP (8123) is the app protocol per ADR-0033; native is migrate-only.
func parseOptions(dsn string) (*clickhouse.Options, error) {
	dsn = strings.TrimSpace(dsn)
	if dsn == "" {
		return nil, fmt.Errorf("clickhouse: empty DSN")
	}
	dsn = normalizeAppDSN(dsn)
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
