package clickhouse

import (
	"fmt"
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
	u, err := url.Parse(dsn)
	if err != nil {
		return nil, fmt.Errorf("clickhouse: parse DSN: %w", err)
	}
	opts := &clickhouse.Options{
		Addr: []string{hostPort(u)},
		Auth: clickhouse.Auth{
			Database: databaseFromURL(u),
			Username: usernameFromURL(u),
			Password: passwordFromURL(u),
		},
		Protocol: protocolForURL(u),
	}
	return opts, nil
}

func hostPort(u *url.URL) string {
	if u.Host != "" {
		return u.Host
	}
	return "localhost:8123"
}

func databaseFromURL(u *url.URL) string {
	if db := strings.Trim(u.Path, "/"); db != "" {
		return db
	}
	if db := u.Query().Get("database"); db != "" {
		return db
	}
	return "ibex"
}

func usernameFromURL(u *url.URL) string {
	if u.User == nil {
		return "default"
	}
	if name := u.User.Username(); name != "" {
		return name
	}
	return "default"
}

func passwordFromURL(u *url.URL) string {
	if u.User == nil {
		return ""
	}
	pass, _ := u.User.Password()
	return pass
}

func protocolForURL(u *url.URL) clickhouse.Protocol {
	scheme := strings.ToLower(u.Scheme)
	if scheme == "http" || scheme == "https" {
		return clickhouse.HTTP
	}
	port := u.Port()
	if port == "8123" || port == "8124" || port == "8443" {
		return clickhouse.HTTP
	}
	return clickhouse.Native
}

// RedactedDSN returns a DSN safe for logging (password stripped).
func RedactedDSN(dsn string) string {
	u, err := url.Parse(dsn)
	if err != nil {
		return "(invalid dsn)"
	}
	if u.User != nil {
		u.User = url.User(u.User.Username())
	}
	return u.String()
}
