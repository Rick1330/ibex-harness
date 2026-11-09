package postgres

import (
	"bytes"
	"errors"
	"regexp"
	"strings"
	"testing"
)

func TestBuildProvisionStatementUsesSCRAM(t *testing.T) {
	const password = `s3cret-Pa'ss\word`
	credential := provisionCredential{
		target:   provisionTarget{role: "ibex_runtime"},
		password: password,
	}
	stmt, err := buildProvisionStatement(credential)
	if err != nil {
		t.Fatalf("buildProvisionStatement: %v", err)
	}
	if strings.Contains(stmt, password) {
		t.Fatalf("plaintext password leaked into statement: %q", stmt)
	}
	pattern := regexp.MustCompile(
		`^ALTER ROLE "ibex_runtime" CONNECTION LIMIT -1 PASSWORD 'SCRAM-SHA-256\$4096:[A-Za-z0-9+/=]+\$[A-Za-z0-9+/=]+:[A-Za-z0-9+/=]+'$`)
	if !pattern.MatchString(stmt) {
		t.Fatalf("statement does not match the SCRAM format: %q", stmt)
	}
}

func TestScramVerifierDeterministicAndStructured(t *testing.T) {
	salt := bytes.Repeat([]byte{0x01}, scramSaltBytes)
	a := scramSHA256Verifier("correct horse battery staple", salt, scramIterations)
	b := scramSHA256Verifier("correct horse battery staple", salt, scramIterations)
	if a != b || !strings.HasPrefix(a, "SCRAM-SHA-256$4096:") {
		t.Fatalf("unexpected verifier: %q vs %q", a, b)
	}
	parts := strings.Split(a, "$")
	if len(parts) != 3 || len(strings.Split(parts[2], ":")) != 2 {
		t.Fatalf("malformed verifier: %q", a)
	}
	if other := scramSHA256Verifier("different", salt, scramIterations); other == a {
		t.Fatal("different passwords produced the same verifier")
	}
}

func TestValidateCapabilityPassword(t *testing.T) {
	tests := []struct {
		name     string
		password string
		wantErr  bool
	}{
		{"valid", `s3cret-Pa'ss\word`, false},
		{"empty", "", true},
		{"space", "two words", true},
		{"tab", "a\tb", true},
		{"non-ascii", "päss", true},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			err := validateCapabilityPassword(tc.password)
			if tc.wantErr && err == nil {
				t.Fatalf("validateCapabilityPassword(%q) = nil, want error", tc.password)
			}
			if !tc.wantErr && err != nil {
				t.Fatalf("validateCapabilityPassword(%q) = %v, want nil", tc.password, err)
			}
		})
	}
}

func TestQuoteLiteral(t *testing.T) {
	tests := []struct {
		in      string
		want    string
		wantErr bool
	}{
		{"s3cret", "'s3cret'", false},
		{"pa'ss", "'pa''ss'", false},
		{`a\b`, `'a\b'`, false},
		{"a\x00b", "", true},
	}
	for _, tc := range tests {
		got, err := quoteLiteral(tc.in)
		if tc.wantErr && err == nil {
			t.Fatalf("quoteLiteral(%q) = %q, want error", tc.in, got)
		}
		if !tc.wantErr && (err != nil || got != tc.want) {
			t.Fatalf("quoteLiteral(%q) = %q, err=%v; want %q", tc.in, got, err, tc.want)
		}
	}
}

func TestQuoteIdent(t *testing.T) {
	if got := quoteIdent("ibex_runtime"); got != `"ibex_runtime"` {
		t.Fatalf("quoteIdent = %q", got)
	}
	if got := quoteIdent(`a"b`); got != `"a""b"` {
		t.Fatalf("quoteIdent = %q", got)
	}
}

func TestResolveProvisionSecrets(t *testing.T) {
	base := map[string]string{
		"IBEX_RUNTIME_DB_PASSWORD":   "runtime",
		"IBEX_WORKER_DB_PASSWORD":    "worker",
		"IBEX_BOOTSTRAP_DB_PASSWORD": "bootstrap",
	}
	tests := []struct {
		name    string
		mutate  func(map[string]string)
		owner   string
		wantErr bool
	}{
		{"ok", nil, "owner", false},
		{"missing", func(e map[string]string) { delete(e, "IBEX_WORKER_DB_PASSWORD") }, "owner", true},
		{"owner collision", func(e map[string]string) { e["IBEX_WORKER_DB_PASSWORD"] = "owner" }, "owner", true},
		{"pairwise", func(e map[string]string) { e["IBEX_WORKER_DB_PASSWORD"] = "runtime" }, "owner", true},
		{"space", func(e map[string]string) { e["IBEX_RUNTIME_DB_PASSWORD"] = "run time" }, "owner", true},
		{"non-ascii", func(e map[string]string) { e["IBEX_RUNTIME_DB_PASSWORD"] = "rün" }, "owner", true},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			env := cloneEnv(base)
			if tc.mutate != nil {
				tc.mutate(env)
			}
			_, err := resolveProvisionSecrets(func(k string) string { return env[k] }, tc.owner)
			if tc.wantErr && err == nil {
				t.Fatal("expected error, got nil")
			}
			if !tc.wantErr && err != nil {
				t.Fatalf("unexpected error: %v", err)
			}
		})
	}
}

func cloneEnv(base map[string]string) map[string]string {
	out := make(map[string]string, len(base))
	for k, v := range base {
		out[k] = v
	}
	return out
}

func TestDSNPassword(t *testing.T) {
	tests := []struct {
		name    string
		dsn     string
		want    string
		wantErr bool
	}{
		{"plain", "postgres://u:p@h:5432/db", "p", false},
		{"encoded", "postgres://u:p%40ss@h/db", "p@ss", false},
		{"missing", "postgres://u@h/db", "", true},
		{"malformed", "://owner-secret", "", true},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			got, err := dsnPassword(tc.dsn)
			if tc.wantErr && err == nil {
				t.Fatalf("dsnPassword(%q) = %q, want error", tc.dsn, got)
			}
			if !tc.wantErr && (err != nil || got != tc.want) {
				t.Fatalf("dsnPassword(%q) = %q, err=%v; want %q", tc.dsn, got, err, tc.want)
			}
			if err != nil && strings.Contains(err.Error(), "owner-secret") {
				t.Fatalf("DSN leaked into the error: %v", err)
			}
		})
	}
}

func TestSanitizeProvisionError(t *testing.T) {
	dsn := "postgres://ibex:owner-secret@host:5432/db"
	secrets := provisionSecrets{"ibex_runtime": "runtime-secret"}
	err := errors.New("failed " + dsn + " with owner-secret and runtime-secret")
	got := sanitizeProvisionError(err, dsn, secrets)
	for _, forbidden := range []string{"owner-secret", "runtime-secret", dsn} {
		if strings.Contains(got.Error(), forbidden) {
			t.Fatalf("sanitized error still contains %q: %q", forbidden, got.Error())
		}
	}
}

func TestRedactError(t *testing.T) {
	for _, tc := range []struct{ name, secret, msg string }{
		{"raw", "sup3r-secret", `syntax error near "'sup3r-secret'"`},
		{"quote-doubled", "pa'ss", `syntax error near "'pa''ss'"`},
	} {
		t.Run(tc.name, func(t *testing.T) {
			got := redactError(errors.New(tc.msg), tc.secret)
			doubled := strings.ReplaceAll(tc.secret, "'", "''")
			if strings.Contains(got.Error(), tc.secret) || strings.Contains(got.Error(), doubled) {
				t.Fatalf("secret survived redaction: %q", got)
			}
		})
	}
	if plain := errors.New("no secret here"); redactError(plain, "sup3r-secret") != plain {
		t.Fatal("expected unchanged error when the secret is absent")
	}
}
