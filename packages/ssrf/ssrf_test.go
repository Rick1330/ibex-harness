package ssrf_test

import (
	"context"
	"net"
	"testing"

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
		{"192.0.2.1", true},
		{"0.0.0.0", true},
	}
	for _, tc := range cases {
		got := ssrf.IsBlockedIP(net.ParseIP(tc.ip))
		if got != tc.blocked {
			t.Fatalf("%s: blocked=%v want %v", tc.ip, got, tc.blocked)
		}
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
	} {
		if err := ssrf.ValidateHTTPURL(ctx, raw); err == nil {
			t.Fatalf("expected deny for %q", raw)
		}
	}
	if err := ssrf.ValidateHTTPURL(ctx, ""); err != nil {
		t.Fatalf("empty ok: %v", err)
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
}
