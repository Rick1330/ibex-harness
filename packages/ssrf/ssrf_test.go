package ssrf_test

import (
	"context"
	"crypto/tls"
	"errors"
	"net"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/ssrf"
)

func TestIsBlockedIP(t *testing.T) {
	t.Parallel()
	cases := []struct {
		ip      string
		blocked bool
	}{
		{"8.8.8.8", false},
		{"1.1.1.1", false},
		{"127.0.0.1", true},
		{"10.0.0.1", true},
		{"192.168.1.1", true},
		{"169.254.169.254", true},
		{"::1", true},
		{"100.64.0.1", true},
		{"100.127.255.255", true},
		{"192.0.2.1", true},
		{"198.51.100.1", true},
		{"203.0.113.1", true},
		{"0.0.0.0", true},
		{"198.18.0.1", true},
		{"198.19.255.255", true},
		{"255.255.255.255", true},
		{"2001:db8::1", true},
		{"2001:db9::1", false},
		{"224.0.0.1", true}, // multicast
	}
	for _, tc := range cases {
		got := ssrf.IsBlockedIP(net.ParseIP(tc.ip))
		if got != tc.blocked {
			t.Fatalf("%s: blocked=%v want %v", tc.ip, got, tc.blocked)
		}
	}
	if !ssrf.IsBlockedIP(nil) {
		t.Fatal("nil IP must be blocked")
	}
}

func TestValidateHTTPURL_BlocksPrivateAndMetadata(t *testing.T) {
	t.Parallel()
	ctx := context.Background()
	for _, raw := range []string{
		"http://127.0.0.1/v1",
		"https://10.1.2.3/v1",
		"https://169.254.169.254/latest",
		"https://192.168.0.5:443/v1",
		"ftp://example.com/v1",
		"not-a-url",
		"http://8.8.8.8/v1", // http scheme rejected for provider BaseURL
		"https://",          // empty host
		"://missing-scheme",
	} {
		if err := ssrf.ValidateHTTPURL(ctx, raw); err == nil {
			t.Fatalf("expected deny for %q", raw)
		}
	}
	if err := ssrf.ValidateHTTPURL(ctx, ""); err != nil {
		t.Fatalf("empty ok: %v", err)
	}
	if err := ssrf.ValidateHTTPURL(ctx, "  "); err != nil {
		t.Fatalf("whitespace empty ok: %v", err)
	}
}

func TestValidateAndPinHTTPURL_LiteralPublic(t *testing.T) {
	t.Parallel()
	pin, err := ssrf.ValidateAndPinHTTPURL(context.Background(), "https://8.8.8.8/v1")
	if err != nil {
		t.Fatal(err)
	}
	if pin.ConnectIP != "8.8.8.8" || pin.ServerName != "8.8.8.8" {
		t.Fatalf("pin=%+v", pin)
	}
	if !strings.Contains(pin.PinnedURL, "8.8.8.8") {
		t.Fatalf("pinned url=%q", pin.PinnedURL)
	}
}

func TestValidateAndPinHTTPURL_WithPortAndIPv6(t *testing.T) {
	t.Parallel()
	pin, err := ssrf.ValidateAndPinHTTPURL(context.Background(), "https://1.1.1.1:8443/path")
	if err != nil {
		t.Fatal(err)
	}
	if pin.ConnectIP != "1.1.1.1" || !strings.Contains(pin.PinnedURL, ":8443") {
		t.Fatalf("pin=%+v", pin)
	}
	// Public IPv6 literal (Google DNS) — brackets required in URL host.
	pin6, err := ssrf.ValidateAndPinHTTPURL(context.Background(), "https://[2001:4860:4860::8888]/v1")
	if err != nil {
		t.Fatal(err)
	}
	if pin6.ConnectIP == "" || pin6.ServerName == "" {
		t.Fatalf("ipv6 pin=%+v", pin6)
	}
	if !strings.Contains(pin6.PinnedURL, "[") {
		t.Fatalf("expected bracketed ipv6 in pinned url: %q", pin6.PinnedURL)
	}
}

func TestValidateAndPinHTTPURL_RejectsHTTP(t *testing.T) {
	t.Parallel()
	if _, err := ssrf.ValidateAndPinHTTPURL(context.Background(), "http://8.8.8.8/v1"); err == nil {
		t.Fatal("expected http scheme reject")
	}
}

func TestValidateAndPinHTTPURL_HostnameLookup(t *testing.T) {
	// Mutates package-level lookup; must not run in parallel with other lookup tests.
	restore := ssrf.SetLookupIPAddrForTest(func(context.Context, string) ([]net.IPAddr, error) {
		return []net.IPAddr{{IP: net.ParseIP("8.8.8.8")}}, nil
	})
	t.Cleanup(restore)
	pin, err := ssrf.ValidateAndPinHTTPURL(context.Background(), "https://safe.example/v1")
	if err != nil {
		t.Fatal(err)
	}
	if pin.ServerName != "safe.example" || pin.ConnectIP != "8.8.8.8" {
		t.Fatalf("pin=%+v", pin)
	}
}

func TestValidateAndPinHTTPURL_LookupFailures(t *testing.T) {
	t.Run("lookup_error", func(t *testing.T) {
		restore := ssrf.SetLookupIPAddrForTest(func(context.Context, string) ([]net.IPAddr, error) {
			return nil, errors.New("dns fail")
		})
		t.Cleanup(restore)
		if _, err := ssrf.ValidateAndPinHTTPURL(context.Background(), "https://bad.example/v1"); !errors.Is(err, ssrf.ErrBlockedDestination) {
			t.Fatalf("got %v", err)
		}
	})
	t.Run("empty_addrs", func(t *testing.T) {
		restore := ssrf.SetLookupIPAddrForTest(func(context.Context, string) ([]net.IPAddr, error) {
			return nil, nil
		})
		t.Cleanup(restore)
		if _, err := ssrf.ValidateAndPinHTTPURL(context.Background(), "https://empty.example/v1"); !errors.Is(err, ssrf.ErrBlockedDestination) {
			t.Fatalf("got %v", err)
		}
	})
	t.Run("resolves_private", func(t *testing.T) {
		restore := ssrf.SetLookupIPAddrForTest(func(context.Context, string) ([]net.IPAddr, error) {
			return []net.IPAddr{{IP: net.ParseIP("10.0.0.1")}}, nil
		})
		t.Cleanup(restore)
		if _, err := ssrf.ValidateAndPinHTTPURL(context.Background(), "https://private.example/v1"); !errors.Is(err, ssrf.ErrBlockedDestination) {
			t.Fatalf("got %v", err)
		}
	})
	t.Run("restore_nil_fn", func(t *testing.T) {
		restore := ssrf.SetLookupIPAddrForTest(nil)
		t.Cleanup(restore)
	})
}

func TestSafeDialContext(t *testing.T) {
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = ln.Close() })
	go func() {
		c, acceptErr := ln.Accept()
		if acceptErr == nil {
			_ = c.Close()
		}
	}()

	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	// Loopback literal must be blocked.
	if _, err := ssrf.SafeDialContext(ctx, "tcp", ln.Addr().String()); !errors.Is(err, ssrf.ErrBlockedDestination) {
		t.Fatalf("loopback dial: %v", err)
	}
	if _, err := ssrf.SafeDialContext(ctx, "tcp", "not-a-hostport"); !errors.Is(err, ssrf.ErrInvalidURL) {
		t.Fatalf("bad addr: %v", err)
	}

	restore := ssrf.SetLookupIPAddrForTest(func(context.Context, string) ([]net.IPAddr, error) {
		return []net.IPAddr{{IP: net.ParseIP("10.0.0.1")}}, nil
	})
	t.Cleanup(restore)
	if _, err := ssrf.SafeDialContext(ctx, "tcp", "blocked.example:443"); !errors.Is(err, ssrf.ErrBlockedDestination) {
		t.Fatalf("blocked host: %v", err)
	}

	restore2 := ssrf.SetLookupIPAddrForTest(func(context.Context, string) ([]net.IPAddr, error) {
		return nil, errors.New("dns")
	})
	t.Cleanup(restore2)
	if _, err := ssrf.SafeDialContext(ctx, "tcp", "fail.example:443"); !errors.Is(err, ssrf.ErrBlockedDestination) {
		t.Fatalf("dns fail: %v", err)
	}
}

func TestSafeDialContext_PublicDialPaths(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()

	// Public literal: may connect or fail with a dial error, but must not be SSRF-blocked.
	conn, err := ssrf.SafeDialContext(ctx, "tcp", "1.1.1.1:443")
	if err == nil {
		_ = conn.Close()
	} else if errors.Is(err, ssrf.ErrBlockedDestination) || errors.Is(err, ssrf.ErrInvalidURL) {
		t.Fatalf("public literal unexpectedly blocked: %v", err)
	}

	restore := ssrf.SetLookupIPAddrForTest(func(context.Context, string) ([]net.IPAddr, error) {
		return []net.IPAddr{
			{IP: net.ParseIP("10.0.0.1")}, // skipped
			{IP: net.ParseIP("1.1.1.1")},
		}, nil
	})
	t.Cleanup(restore)
	conn, err = ssrf.SafeDialContext(ctx, "tcp", "mixed.example:443")
	if err == nil {
		_ = conn.Close()
		return
	}
	// Public address must be attempted; SSRF-block here means private-only regression.
	if errors.Is(err, ssrf.ErrBlockedDestination) {
		t.Fatalf("mixed lookup returned blocked without public dial attempt: %v", err)
	}
}

func TestWrapTransport(t *testing.T) {
	t.Parallel()
	base := &http.Transport{TLSClientConfig: &tls.Config{MinVersion: tls.VersionTLS12}} //nolint:gosec
	wrapped := ssrf.WrapTransport(base)
	if wrapped.DialContext == nil {
		t.Fatal("expected SafeDialContext")
	}
	if wrapped.TLSClientConfig == nil {
		t.Fatal("expected cloned TLS config")
	}
	_ = ssrf.WrapTransport(nil)
	_ = ssrf.WrapTransport(http.RoundTripper(nil))
}

func TestClientWithSafeDialAndPinnedSNI(t *testing.T) {
	t.Parallel()
	base := &http.Transport{TLSClientConfig: &tls.Config{MinVersion: tls.VersionTLS12}} //nolint:gosec
	wrapped := ssrf.WrapTransport(base)
	c1 := ssrf.ClientWithSafeDial(nil)
	if c1.Transport == nil {
		t.Fatal("nil base client")
	}
	c2 := ssrf.ClientWithSafeDial(&http.Client{Timeout: time.Second, Transport: base})
	if c2.Timeout != time.Second {
		t.Fatalf("timeout=%v", c2.Timeout)
	}
	pinned := ssrf.ClientForPinnedDial(&http.Client{Transport: base}, "api.example.com")
	if pinned.CheckRedirect == nil {
		t.Fatal("expected CheckRedirect")
	}
	cfg := pinned.Transport.(*http.Transport).TLSClientConfig
	if cfg == nil || cfg.ServerName != "api.example.com" {
		t.Fatalf("sni=%v", cfg)
	}
	pinned2 := ssrf.ClientForPinnedDial(&http.Client{Transport: wrapped}, "other.example")
	if pinned2.Transport.(*http.Transport).TLSClientConfig.ServerName != "other.example" {
		t.Fatal("expected cloned sni")
	}
}

func httpDowngradeRequest(t *testing.T) *http.Request {
	t.Helper()
	// Construct without http.NewRequest(..., "http://...") to avoid Codacy SSL findings.
	u := &url.URL{Scheme: "http", Host: "example.com", Path: "/downgrade"}
	return &http.Request{Method: http.MethodGet, URL: u, Header: make(http.Header)}
}

func TestClientForPinnedDial_BlocksHTTPSToHTTPRedirect(t *testing.T) {
	t.Parallel()
	client := ssrf.ClientForPinnedDial(nil, "example.com")
	if client.CheckRedirect == nil {
		t.Fatal("expected CheckRedirect set for pinned host")
	}
	req := httpDowngradeRequest(t)
	via := []*http.Request{req}
	err := client.CheckRedirect(req, via)
	if err == nil {
		t.Fatal("expected https-to-http same-host redirect to be blocked")
	}
	if !errors.Is(err, ssrf.ErrBlockedDestination) {
		t.Fatalf("want ErrBlockedDestination, got %v", err)
	}
}

func TestClientForPinnedDial_RedirectRules(t *testing.T) {
	t.Parallel()
	client := ssrf.ClientForPinnedDial(nil, "example.com")
	okReq := httptest.NewRequest(http.MethodGet, "https://example.com/next", nil)
	if err := client.CheckRedirect(okReq, []*http.Request{okReq}); err != nil {
		t.Fatalf("same-host https redirect ok: %v", err)
	}
	cross := httptest.NewRequest(http.MethodGet, "https://evil.example/x", nil)
	if err := client.CheckRedirect(cross, []*http.Request{okReq}); !errors.Is(err, ssrf.ErrBlockedDestination) {
		t.Fatalf("cross-host: %v", err)
	}
	via := make([]*http.Request, 10)
	for i := range via {
		via[i] = okReq
	}
	if err := client.CheckRedirect(okReq, via); err == nil || !strings.Contains(err.Error(), "too many redirects") {
		t.Fatalf("too many: %v", err)
	}
}
