package logger

import (
	"bytes"
	"context"
	"encoding/json"
	"log/slog"
	"strings"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/reqid"
)

func testLogger(t *testing.T, buf *bytes.Buffer) *Logger {
	t.Helper()
	log, err := New(Config{Service: "proxy", Level: slog.LevelDebug, Writer: buf})
	if err != nil {
		t.Fatal(err)
	}
	return log
}

func parseLogLine(t *testing.T, buf *bytes.Buffer) map[string]any {
	t.Helper()
	var out map[string]any
	if err := json.Unmarshal(buf.Bytes(), &out); err != nil {
		t.Fatalf("json unmarshal: %v raw=%q", err, buf.String())
	}
	return out
}

func TestLogger_JSONFormat(t *testing.T) {
	var buf bytes.Buffer
	log := testLogger(t, &buf)
	log.InfoCtx(context.Background(), "hello", "org_id", "oid")
	out := parseLogLine(t, &buf)
	for _, key := range []string{"timestamp", "level", "service", "request_id", "trace_id", "message"} {
		if _, ok := out[key]; !ok {
			t.Fatalf("missing field %q: %v", key, out)
		}
	}
	if out["service"] != "proxy" {
		t.Fatalf("service: %v", out["service"])
	}
	if out["message"] != "hello" {
		t.Fatalf("message: %v", out["message"])
	}
}

func TestLogger_RequestIDFromContext(t *testing.T) {
	var buf bytes.Buffer
	log := testLogger(t, &buf)
	ctx := reqid.WithRequestID(context.Background(), "550e8400-e29b-41d4-a716-446655440000")
	log.InfoCtx(ctx, "with req")
	out := parseLogLine(t, &buf)
	if out["request_id"] != "550e8400-e29b-41d4-a716-446655440000" {
		t.Fatalf("request_id: %v", out["request_id"])
	}
}

func TestLogger_NoRequestID(t *testing.T) {
	var buf bytes.Buffer
	log := testLogger(t, &buf)
	log.InfoCtx(context.Background(), "no req")
	out := parseLogLine(t, &buf)
	if _, ok := out["request_id"]; !ok {
		t.Fatal("request_id field should be present")
	}
	if out["request_id"] != "" {
		t.Fatalf("request_id: %v", out["request_id"])
	}
}

func TestLogger_ForbiddenField(t *testing.T) {
	var buf bytes.Buffer
	log := testLogger(t, &buf)
	log.InfoCtx(context.Background(), "secret log", "token", "sk-live-secret")
	out := parseLogLine(t, &buf)
	raw := buf.String()
	if strings.Contains(raw, "sk-live-secret") {
		t.Fatalf("forbidden value leaked: %s", raw)
	}
	if out["token"] != "[REDACTED]" {
		t.Fatalf("token: %v", out["token"])
	}
}

func TestLogger_NoGlobalState(t *testing.T) {
	var bufA bytes.Buffer
	var bufB bytes.Buffer
	logA, err := New(Config{Service: "auth", Writer: &bufA})
	if err != nil {
		t.Fatal(err)
	}
	logB, err := New(Config{Service: "proxy", Writer: &bufB})
	if err != nil {
		t.Fatal(err)
	}
	logA.InfoCtx(context.Background(), "auth line")
	logB.InfoCtx(context.Background(), "proxy line")
	outA := parseLogLine(t, &bufA)
	outB := parseLogLine(t, &bufB)
	if outA["service"] != "auth" || outB["service"] != "proxy" {
		t.Fatalf("services mixed: %v %v", outA["service"], outB["service"])
	}
}
