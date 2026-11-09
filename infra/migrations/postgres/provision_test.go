package postgres

import (
	"bytes"
	"errors"
	"regexp"
	"strings"
	"testing"
)

func TestBuildProvisionStatementUsesSCRAMAndOmitsPassword(t *testing.T) {
	const password = `s3cret-Pa'ss\word`
	stmt, err := buildProvisionStatement("ibex_runtime", password)
	if err != nil {
		t.Fatalf("buildProvisionStatement: %v", err)
	}
	if !strings.HasPrefix(stmt, `ALTER ROLE "ibex_runtime" PASSWORD 'SCRAM-SHA-256$4096:`) {
		t.Fatalf("unexpected statement shape: %q", stmt)
	}
	if strings.Contains(stmt, password) {
		t.Fatalf("plaintext password leaked into statement: %q", stmt)
	}
	pattern := regexp.MustCompile(
		`^ALTER ROLE "ibex_runtime" PASSWORD 'SCRAM-SHA-256\$4096:[A-Za-z0-9+/=]+\$[A-Za-z0-9+/=]+:[A-Za-z0-9+/=]+'$`)
	if !pattern.MatchString(stmt) {
		t.Fatalf("statement does not match the SCRAM format: %q", stmt)
	}
}

func TestScramVerifierDeterministicAndStructured(t *testing.T) {
	salt := bytes.Repeat([]byte{0x01}, scramSaltBytes)
	a := scramSHA256Verifier("correct horse battery staple", salt, scramIterations)
	b := scramSHA256Verifier("correct horse battery staple", salt, scramIterations)
	if a != b {
		t.Fatal("expected a deterministic verifier for a fixed salt")
	}
	if !strings.HasPrefix(a, "SCRAM-SHA-256$4096:") {
		t.Fatalf("unexpected verifier prefix: %q", a)
	}
	parts := strings.Split(a, "$")
	if len(parts) != 3 {
		t.Fatalf("expected 3 SCRAM segments, got %d in %q", len(parts), a)
	}
	keys := strings.Split(parts[2], ":")
	if len(keys) != 2 {
		t.Fatalf("expected stored:server key pair, got %q", parts[2])
	}
	for _, part := range []string{strings.TrimPrefix(parts[1], "4096:"), keys[0], keys[1]} {
		if part == "" {
			t.Fatalf("empty SCRAM component in %q", a)
		}
	}
	if other := scramSHA256Verifier("different", salt, scramIterations); other == a {
		t.Fatal("different passwords produced the same verifier")
	}
}

func TestQuoteLiteral(t *testing.T) {
	tests := []struct {
		name    string
		in      string
		want    string
		wantErr bool
	}{
		{name: "plain", in: "s3cret", want: "'s3cret'"},
		{name: "single quote", in: "pa'ss", want: "'pa''ss'"},
		{name: "backslash is literal", in: `a\b`, want: `'a\b'`},
		{name: "nul rejected", in: "a\x00b", wantErr: true},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			got, err := quoteLiteral(tc.in)
			if tc.wantErr {
				if err == nil {
					t.Fatalf("expected error, got %q", got)
				}
				return
			}
			if err != nil {
				t.Fatalf("quoteLiteral: %v", err)
			}
			if got != tc.want {
				t.Fatalf("quoteLiteral(%q) = %q, want %q", tc.in, got, tc.want)
			}
		})
	}
}

func TestQuoteIdent(t *testing.T) {
	if got, want := quoteIdent("ibex_runtime"), `"ibex_runtime"`; got != want {
		t.Fatalf("quoteIdent = %q, want %q", got, want)
	}
	if got, want := quoteIdent(`a"b`), `"a""b"`; got != want {
		t.Fatalf("quoteIdent = %q, want %q", got, want)
	}
}

func TestResolveProvisionSecrets(t *testing.T) {
	env := map[string]string{
		"POSTGRES_PASSWORD":          "owner",
		"IBEX_RUNTIME_DB_PASSWORD":   "runtime",
		"IBEX_WORKER_DB_PASSWORD":    "worker",
		"IBEX_BOOTSTRAP_DB_PASSWORD": "bootstrap",
	}
	got, err := resolveProvisionSecrets(func(k string) string { return env[k] })
	if err != nil {
		t.Fatalf("resolveProvisionSecrets: %v", err)
	}
	if got["ibex_runtime"] != "runtime" || got["ibex_worker"] != "worker" || got["ibex_bootstrap"] != "bootstrap" {
		t.Fatalf("unexpected secrets map: %#v", got)
	}

	delete(env, "IBEX_WORKER_DB_PASSWORD")
	if _, err := resolveProvisionSecrets(func(k string) string { return env[k] }); err == nil {
		t.Fatal("expected missing-secret error")
	}

	env["IBEX_WORKER_DB_PASSWORD"] = "owner"
	if _, err := resolveProvisionSecrets(func(k string) string { return env[k] }); err == nil {
		t.Fatal("expected owner-password collision error")
	}
}

func TestRedactError(t *testing.T) {
	secret := "sup3r-secret"
	err := errors.New(`syntax error near "'sup3r-secret'"`)
	got := redactError(err, secret)
	if strings.Contains(got.Error(), secret) {
		t.Fatalf("secret survived redaction: %q", got)
	}
	if !strings.Contains(got.Error(), "[redacted]") {
		t.Fatalf("expected [redacted] marker, got %q", got)
	}

	plain := errors.New("no secret here")
	if redactError(plain, secret) != plain {
		t.Fatal("expected unchanged error when the secret is absent")
	}
}
