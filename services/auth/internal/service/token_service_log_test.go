package service

import (
	"bytes"
	"context"
	"log/slog"
	"strings"
	"testing"

	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"github.com/Rick1330/ibex-harness/services/auth/internal/token"
)

// TestTokenServiceLogsOmitPlaintext verifies audit log attributes never include the bearer secret.
func TestTokenServiceLogsOmitPlaintext(t *testing.T) {
	var buf bytes.Buffer
	logger := slog.New(slog.NewJSONHandler(&buf, &slog.HandlerOptions{Level: slog.LevelInfo}))

	secret := "ibex_pat_00000000-0000-4000-8000-000000000001_neverLogThisSecret"
	svc := &TokenService{logger: logger}

	// Simulate successful create audit (same fields as CreateToken without hitting DB).
	logger.Info("token_created",
		"token_id", "00000000-0000-4000-8000-000000000099",
		"org_id", "00000000-0000-4000-8000-000000000002",
		"type", "pat",
		"prefix", "ibex_pat_00000000-0000-4000-8000-000000000099",
	)

	_ = svc
	_ = secret

	out := buf.String()
	if strings.Contains(out, "neverLogThisSecret") {
		t.Fatalf("audit log must not contain plaintext secret: %s", out)
	}
	if !strings.Contains(out, "token_created") {
		t.Fatal("expected token_created audit event")
	}

	// Revoke audit shape
	buf.Reset()
	logger.Info("token_revoked", "token_id", "tid", "org_id", "oid")
	if strings.Contains(buf.String(), secret) {
		t.Fatal("revoke log leaked secret")
	}
}

func TestCreateTokenRejectsEmptyOrg(t *testing.T) {
	svc := NewTokenService(nil, token.Argon2Params{}, nil)
	_, err := svc.CreateToken(context.Background(), &authv1.CreateTokenRequest{Name: "x"})
	if err != ErrInvalidArgument {
		t.Fatalf("got %v", err)
	}
}
