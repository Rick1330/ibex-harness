package config

import (
	"io"
	"os"
	"strings"
	"testing"

	ibexconfig "github.com/Rick1330/ibex-harness/packages/config"
)

// TestLogDebug_RedactsGRPCTLSPaths pins the debug-dump contract: the
// AuthService gRPC certificate and key paths must not appear in the resolved
// configuration log, even though the paths are not key material.
func TestLogDebug_RedactsGRPCTLSPaths(t *testing.T) {
	const certPath = "/run/secrets/ibex-auth-grpc.crt"
	const keyPath = "/run/secrets/ibex-auth-grpc.key"

	cfg := envConfig{
		Environment:     "production",
		GRPCTLSCertFile: certPath,
		GRPCTLSKeyFile:  keyPath,
	}

	out := captureStderr(t, func() { ibexconfig.LogDebug(cfg) })
	for _, path := range []string{certPath, keyPath} {
		if strings.Contains(out, path) {
			t.Fatalf("resolved-config log leaked %s: %s", path, out)
		}
	}
	if !strings.Contains(out, "[REDACTED]") {
		t.Fatalf("expected redaction marker in log: %s", out)
	}
}

func captureStderr(t *testing.T, fn func()) string {
	t.Helper()
	r, w, err := os.Pipe()
	if err != nil {
		t.Fatal(err)
	}
	old := os.Stderr
	os.Stderr = w
	t.Cleanup(func() {
		os.Stderr = old
		_ = w.Close() //nolint:errcheck // test teardown restores stderr
	})

	outCh := make(chan string, 1)
	go func() {
		var buf strings.Builder
		_, copyErr := io.Copy(&buf, r)
		_ = r.Close() //nolint:errcheck // drain pipe after copy
		if copyErr != nil {
			outCh <- ""
			return
		}
		outCh <- buf.String()
	}()

	fn()
	_ = w.Close() //nolint:errcheck // signal EOF to reader goroutine
	return <-outCh
}
