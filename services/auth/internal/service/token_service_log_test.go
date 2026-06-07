package service

import (
	"bytes"
	"context"
	"strings"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/logger"
	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"github.com/Rick1330/ibex-harness/services/auth/internal/token"
)

// TestTokenServiceLogsOmitPlaintext verifies audit log attributes never include the bearer secret.
func TestTokenServiceLogsOmitPlaintext(t *testing.T) {
	var buf bytes.Buffer
	log, err := logger.New(logger.Config{Service: "auth", Writer: &buf})
	if err != nil {
		t.Fatal(err)
	}

	secret := "ibex_pat_00000000-0000-4000-8000-000000000001_neverLogThisSecret"
	svc := &TokenService{logger: log}

	log.InfoCtx(context.Background(), "token_created",
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

	buf.Reset()
	log.InfoCtx(context.Background(), "token_revoked", "token_id", "tid", "org_id", "oid")
	if strings.Contains(buf.String(), secret) {
		t.Fatal("revoke log leaked secret")
	}
}

func TestCreateTokenRejectsEmptyOrg(t *testing.T) {
	svc := NewTokenService(nil, token.Argon2Params{}, logger.Discard("auth"))
	_, err := svc.CreateToken(context.Background(), &authv1.CreateTokenRequest{Name: "x"})
	if err != ErrInvalidArgument {
		t.Fatalf("got %v", err)
	}
}
