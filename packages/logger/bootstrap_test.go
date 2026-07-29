package logger

import (
	"errors"
	"io"
	"os"
	"strings"
	"testing"
)

func captureStderr(t *testing.T, fn func()) string {
	t.Helper()
	r, w, err := os.Pipe()
	if err != nil {
		t.Fatalf("pipe: %v", err)
	}
	old := os.Stderr
	os.Stderr = w
	t.Cleanup(func() {
		os.Stderr = old
		_ = w.Close() //nolint:errcheck // test teardown restores stderr
		_ = r.Close() //nolint:errcheck // drain pipe after capture
	})

	fn()
	_ = w.Close() //nolint:errcheck // signal EOF to reader
	out, err := io.ReadAll(r)
	if err != nil {
		t.Fatalf("read stderr: %v", err)
	}
	return string(out)
}

func TestUnit_BootstrapError_WritesStructuredLog(t *testing.T) {
	// Must not run in parallel: captureStderr mutates process-wide os.Stderr.
	out := captureStderr(t, func() {
		BootstrapError("boom", errors.New("bad"))
	})

	if !strings.Contains(out, `"msg":"boom"`) {
		t.Fatalf("missing message: %s", out)
	}
	if !strings.Contains(out, `"error":"bad"`) {
		t.Fatalf("missing error field: %s", out)
	}
}

func TestUnit_BootstrapDebug_WritesStructuredLog(t *testing.T) {
	// Must not run in parallel: captureStderr mutates process-wide os.Stderr.
	out := captureStderr(t, func() {
		BootstrapDebug("dbg", "k", "v")
	})

	if !strings.Contains(out, `"msg":"dbg"`) {
		t.Fatalf("missing message: %s", out)
	}
	if !strings.Contains(out, `"k":"v"`) {
		t.Fatalf("missing key/value: %s", out)
	}
}
