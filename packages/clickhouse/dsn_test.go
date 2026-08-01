package clickhouse

import (
	"strings"
	"testing"

	ch "github.com/ClickHouse/clickhouse-go/v2"
)

func TestUnit_DSN_ProtocolSelection(t *testing.T) {
	t.Parallel()
	cases := []struct {
		name     string
		dsn      string
		wantHTTP bool
	}{
		{name: "http_8123", dsn: "clickhouse://default:@localhost:8123/ibex", wantHTTP: true},
		{name: "http_scheme", dsn: "http://default:@localhost:8123/ibex", wantHTTP: true},
		{name: "ipv6_8123", dsn: "clickhouse://default:@[::1]:8123/ibex", wantHTTP: true},
		{name: "http_8124", dsn: "clickhouse://default:@localhost:8124/ibex", wantHTTP: true},
		{name: "http_8443", dsn: "clickhouse://default:@localhost:8443/ibex", wantHTTP: true},
		{name: "native_9000", dsn: "clickhouse://default:@localhost:9000/ibex", wantHTTP: false},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			opts, err := parseOptions(tc.dsn)
			if err != nil {
				t.Fatal(err)
			}
			gotHTTP := opts.Protocol == ch.HTTP
			if gotHTTP != tc.wantHTTP {
				t.Fatalf("protocol HTTP=%v want %v", gotHTTP, tc.wantHTTP)
			}
		})
	}
}

func TestUnit_DSN_DefaultDatabase(t *testing.T) {
	t.Parallel()
	opts, err := parseOptions("clickhouse://default:@localhost:8123")
	if err != nil {
		t.Fatal(err)
	}
	if opts.Auth.Database != "ibex" {
		t.Fatalf("db=%s", opts.Auth.Database)
	}
}

func TestUnit_DSN_UserinfoPasswordFlattens(t *testing.T) {
	t.Parallel()
	opts, err := parseOptions("clickhouse://default:ibexdev@localhost:8123/ibex")
	if err != nil {
		t.Fatal(err)
	}
	if opts.Auth.Username != "default" {
		t.Fatalf("username=%s", opts.Auth.Username)
	}
	if opts.Auth.Password != "ibexdev" {
		t.Fatalf("password not applied from userinfo")
	}
	if opts.Auth.Database != "ibex" {
		t.Fatalf("db=%s", opts.Auth.Database)
	}
	if opts.Protocol != ch.HTTP {
		t.Fatal("want HTTP protocol for :8123")
	}
}

func TestUnit_NormalizeAppDSN_RewritesHTTPScheme(t *testing.T) {
	t.Parallel()
	got := normalizeAppDSN("clickhouse://default:secret@localhost:8123/ibex")
	if !strings.HasPrefix(got, "http://") {
		t.Fatalf("got %q", got)
	}
	if strings.Contains(got, "secret@") {
		t.Fatalf("userinfo password leaked: %q", got)
	}
	if !strings.Contains(got, "password=secret") {
		t.Fatalf("password query missing: %q", got)
	}
}

func TestUnit_DSN_Empty(t *testing.T) {
	t.Parallel()
	if _, err := parseOptions("  "); err == nil {
		t.Fatal("expected error")
	}
}

func TestUnit_DSN_ParseError(t *testing.T) {
	t.Parallel()
	_, err := parseOptions("clickhouse://[::1")
	if err == nil || !strings.Contains(err.Error(), "parse DSN") {
		t.Fatalf("got %v", err)
	}
}

func TestUnit_HTTPAppPort_BareHost(t *testing.T) {
	t.Parallel()
	if httpAppPort("localhost") {
		t.Fatal("bare host must not force HTTP")
	}
	if httpAppPort("localhost:9000") {
		t.Fatal("native port must not force HTTP")
	}
}

func TestUnit_RedactedDSN(t *testing.T) {
	t.Parallel()
	got := RedactedDSN("clickhouse://default:secret@localhost:8123/ibex?password=also")
	if strings.Contains(got, "secret") || strings.Contains(got, "also") {
		t.Fatalf("got %q", got)
	}
	got2 := RedactedDSN("clickhouse://u@h:8123/ibex?passwd=hidden")
	if strings.Contains(got2, "hidden") {
		t.Fatalf("passwd query leaked: %q", got2)
	}
	if RedactedDSN("://") != "(invalid dsn)" {
		t.Fatal("invalid dsn sentinel")
	}
	if RedactedDSN("not-a-url") != "(invalid dsn)" {
		t.Fatal("schemeless sentinel")
	}
}
