package logger

import (
	"log/slog"
	"testing"
)

func TestRedactAttr_forbiddenKeys(t *testing.T) {
	t.Parallel()

	for _, key := range []string{
		"token", "password", "hash", "content", "email", "ip",
		"secret", "key", "credential", "bearer", "authorization",
		"access_token", "refresh_token", "api_key", "private_key", "session_token",
		// Normalized forms (case / hyphen → underscore)
		"Authorization", "Bearer", "Access-Token",
	} {
		attr := redactAttr(slog.String(key, "leak-value"))
		if attr.Value.String() != "[REDACTED]" {
			t.Fatalf("%s: got %q", key, attr.Value.String())
		}
	}
}

func TestRedactAttr_safeKeysPassThrough(t *testing.T) {
	t.Parallel()

	attr := redactAttr(slog.String("org_id", "550e8400-e29b-41d4-a716-446655440000"))
	if attr.Value.String() != "550e8400-e29b-41d4-a716-446655440000" {
		t.Fatalf("org_id: %q", attr.Value.String())
	}
}
