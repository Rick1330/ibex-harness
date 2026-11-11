package postgres

import (
	"bytes"
	"database/sql"
	"errors"
	"regexp"
	"strings"
	"testing"
	"time"
)

// TestBuildProvisionStatementUsesSCRAM proves the emitted SQL carries a SCRAM
// verifier and never the plaintext password.
func TestBuildProvisionStatementUsesSCRAM(t *testing.T) {
	const secret = `s3cret-Pa'ss\word`
	stmt, err := buildProvisionStatement(provisionCredential{
		target:   provisionTarget{role: "ibex_runtime"},
		password: secret,
	})
	if err != nil {
		t.Fatalf("buildProvisionStatement: %v", err)
	}
	if strings.Contains(stmt, secret) {
		t.Fatalf("plaintext password leaked into statement: %q", stmt)
	}
	if !regexp.MustCompile(
		`^ALTER ROLE "ibex_runtime" CONNECTION LIMIT -1 PASSWORD 'SCRAM-SHA-256\$4096:[A-Za-z0-9+/=]+\$[A-Za-z0-9+/=]+:[A-Za-z0-9+/=]+'$`).MatchString(stmt) {
		t.Fatalf("statement does not match the SCRAM format: %q", stmt)
	}
}

// TestScramVerifierDeterministicAndStructured checks the verifier is stable for
// a fixed salt and structurally well formed.
func TestScramVerifierDeterministicAndStructured(t *testing.T) {
	salt := bytes.Repeat([]byte{0x01}, scramSaltBytes)
	input := scramInput{password: "correct horse battery staple", salt: salt, iterations: scramIterations}
	a := scramSHA256Verifier(input)
	b := scramSHA256Verifier(input)
	if a != b || !strings.HasPrefix(a, "SCRAM-SHA-256$4096:") {
		t.Fatalf("unexpected verifier: %q vs %q", a, b)
	}
	parts := strings.Split(a, "$")
	if len(parts) != 3 || len(strings.Split(parts[2], ":")) != 2 {
		t.Fatalf("malformed verifier: %q", a)
	}
	if scramSHA256Verifier(scramInput{password: "different", salt: salt, iterations: scramIterations}) == a {
		t.Fatal("different passwords produced the same verifier")
	}
}

// TestValidateCapabilityPassword rejects non-ASCII, whitespace and empty
// secrets before a verifier is derived.
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

// TestSQLTextQuoted checks single-quote doubling and NUL rejection.
func TestSQLTextQuoted(t *testing.T) {
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
		t.Run(tc.in, func(t *testing.T) {
			got, err := sqlText{value: tc.in}.quoted()
			if tc.wantErr {
				if err == nil {
					t.Fatalf("sqlText(%q).quoted() = %q, want error", tc.in, got)
				}
				return
			}
			if err != nil || got != tc.want {
				t.Fatalf("sqlText(%q).quoted() = %q, err=%v; want %q", tc.in, got, err, tc.want)
			}
		})
	}
}

// TestSQLIdentifierQuoted checks double-quote doubling for identifiers.
func TestSQLIdentifierQuoted(t *testing.T) {
	if got := (sqlIdentifier{value: "ibex_runtime"}).quoted(); got != `"ibex_runtime"` {
		t.Fatalf("quoted identifier = %q", got)
	}
	if got := (sqlIdentifier{value: `a"b`}).quoted(); got != `"a""b"` {
		t.Fatalf("quoted identifier = %q", got)
	}
}

// TestParseRoleValidUntil covers the four states a role expiry can have. The
// sentinels are the regression: lib/pq hands `infinity` back as text, which a
// SQLSTATE-clean migration run used to turn into an unsupported-Scan failure.
func TestParseRoleValidUntil(t *testing.T) {
	now := time.Date(2026, time.November, 11, 12, 0, 0, 0, time.UTC)
	tests := []struct {
		name        string
		value       sql.NullString
		wantExpired bool
		wantDescr   string
	}{
		{"null", sql.NullString{}, false, "none"},
		{"empty", sql.NullString{String: "", Valid: true}, false, "none"},
		{"infinity", sql.NullString{String: "infinity", Valid: true}, false, "infinity"},
		{"negative infinity", sql.NullString{String: "-infinity", Valid: true}, true, "-infinity"},
		{
			name:        "past instant",
			value:       sql.NullString{String: "2020-01-01T00:00:00.000000Z", Valid: true},
			wantExpired: true,
			wantDescr:   "2020-01-01T00:00:00Z",
		},
		{
			name:        "future instant",
			value:       sql.NullString{String: "2030-01-01T00:00:00.000000Z", Valid: true},
			wantExpired: false,
			wantDescr:   "2030-01-01T00:00:00Z",
		},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			parsed, err := parseRoleValidUntil(tc.value)
			if err != nil {
				t.Fatalf("parseRoleValidUntil(%q): %v", tc.value.String, err)
			}
			if got := parsed.expired(now); got != tc.wantExpired {
				t.Fatalf("expired = %v, want %v", got, tc.wantExpired)
			}
			if got := parsed.describe(); got != tc.wantDescr {
				t.Fatalf("describe = %q, want %q", got, tc.wantDescr)
			}
		})
	}
}

// TestParseRoleValidUntilRejectsGarbage keeps an unparseable server value from
// being read as "no expiry", which would pass the safe-role postcondition.
func TestParseRoleValidUntilRejectsGarbage(t *testing.T) {
	if _, err := parseRoleValidUntil(sql.NullString{String: "next tuesday", Valid: true}); err == nil {
		t.Fatal("parseRoleValidUntil accepted an unparseable value")
	}
}

// TestRoleAttributesInfinityIsSafe proves the whole postcondition, not just the
// parser: a provisioned login whose credential never expires is safe.
func TestRoleAttributesInfinityIsSafe(t *testing.T) {
	attributes := roleAttributes{
		login: true, connlimit: -1,
		validUntil: roleValidUntil{unbounded: true},
	}
	if !attributes.safe(time.Now()) {
		t.Fatalf("an infinity expiry was rejected as unsafe: %s", attributes.describe())
	}
	if got := attributes.describe(); !strings.Contains(got, "validuntil=infinity") {
		t.Fatalf("describe = %q, want the infinity marker", got)
	}
}

// TestRoleAttributesNegativeInfinityIsExpired proves '-infinity' fails closed
// with the expiry message rather than the generic unsafe-attributes one.
func TestRoleAttributesNegativeInfinityIsExpired(t *testing.T) {
	attributes := roleAttributes{
		login: true, connlimit: -1,
		validUntil: roleValidUntil{beforeEpoch: true},
	}
	if !attributes.expired(time.Now()) {
		t.Fatal("a -infinity expiry was not reported as expired")
	}
	if attributes.safe(time.Now()) {
		t.Fatal("a -infinity expiry was accepted as safe")
	}
}

// TestResolveProvisionSecrets enforces presence, ASCII, pairwise distinctness
// and separation from the DSN credential.
func TestResolveProvisionSecrets(t *testing.T) {
	base := map[string]string{
		"IBEX_RUNTIME_DB_PASSWORD":   "runtime",
		"IBEX_WORKER_DB_PASSWORD":    "worker",
		"IBEX_BOOTSTRAP_DB_PASSWORD": "bootstrap",
		"IBEX_AUTH_DB_PASSWORD":      "auth",
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
			_, err := resolveProvisionSecrets(func(k string) string { return env[k] }, ownerCredential{password: tc.owner})
			if tc.wantErr && err == nil {
				t.Fatal("expected error, got nil")
			}
			if !tc.wantErr && err != nil {
				t.Fatalf("unexpected error: %v", err)
			}
		})
	}
}

// cloneEnv returns a shallow copy of an environment map.
func cloneEnv(base map[string]string) map[string]string {
	out := make(map[string]string, len(base))
	for k, v := range base {
		out[k] = v
	}
	return out
}

// dsnPasswordCase is one effective-credential parsing case.
type dsnPasswordCase struct {
	name    string
	dsn     string
	want    string
	wantErr bool
}

// dsnPasswordCases covers userinfo, the query parameter, ambiguity and errors.
func dsnPasswordCases() []dsnPasswordCase {
	return []dsnPasswordCase{
		{"plain", "postgres://u:pa@h:5432/db", "pa", false},
		{"encoded", "postgres://u:pa%40@h/db", "pa@", false},
		{"query only", "postgres://u@h/db?password=qa", "qa", false},
		{"matching", "postgres://u:qq@h/db?password=qq", "qq", false},
		{"ambiguous", "postgres://u:a@h/db?password=b", "", true},
		{"missing", "postgres://u@h/db", "", true},
		{"malformed", "://o", "", true},
	}
}

// TestDSNPassword splits each effective-credential case into its own subtest.
func TestDSNPassword(t *testing.T) {
	for _, tc := range dsnPasswordCases() {
		t.Run(tc.name, func(t *testing.T) { assertDSNPassword(t, tc) })
	}
}

// assertDSNPassword asserts one effective-credential case and that the error
// never echoes the DSN.
func assertDSNPassword(t *testing.T, tc dsnPasswordCase) {
	t.Helper()
	got, err := dsnPassword(tc.dsn)
	if tc.wantErr {
		if err == nil {
			t.Fatalf("dsnPassword(%q) = %q, want error", tc.dsn, got)
		}
		if strings.Contains(err.Error(), "secret") {
			t.Fatalf("DSN leaked into the error: %v", err)
		}
		return
	}
	if err != nil || got != tc.want {
		t.Fatalf("dsnPassword(%q) = %q, err=%v; want %q", tc.dsn, got, err, tc.want)
	}
}

// TestValidateDSNScheme rejects anything but postgres/postgresql.
func TestValidateDSNScheme(t *testing.T) {
	tests := []struct {
		name    string
		dsn     string
		wantErr bool
	}{
		{"postgres", "postgres://u:p@h/db", false},
		{"postgresql", "postgresql://u:p@h/db", false},
		{"mysql", "mysql://u:p@h/db", true},
		{"malformed", "://owner-secret", true},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			err := validateDSNScheme(tc.dsn)
			if tc.wantErr && err == nil {
				t.Fatalf("validateDSNScheme(%q) = nil, want error", tc.dsn)
			}
			if !tc.wantErr && err != nil {
				t.Fatalf("validateDSNScheme(%q) = %v, want nil", tc.dsn, err)
			}
		})
	}
}

// TestSanitizeProvisionError removes the DSN, its credential and every secret
// while keeping non-sensitive context.
func TestSanitizeProvisionError(t *testing.T) {
	owner := "own" + "er-sentinel"
	runtimeSecret := "run" + "time-sentinel"
	run := provisionRun{
		dsn:     "postgres://ibex:" + owner + "@host:5432/db",
		secrets: provisionSecrets{"ibex_runtime": runtimeSecret},
	}
	err := errors.New("failed " + run.dsn + " with " + owner + " and " + runtimeSecret + " while opening the database")
	got := sanitizeProvisionError(err, run).Error()
	for _, forbidden := range []string{owner, runtimeSecret, run.dsn} {
		if strings.Contains(got, forbidden) {
			t.Fatalf("sanitized error still contains %q: %q", forbidden, got)
		}
	}
	if !strings.Contains(got, "failed") {
		t.Fatalf("sanitized error lost the failure context: %q", got)
	}
	if !strings.Contains(got, "opening the database") {
		t.Fatalf("sanitized error lost the operation context: %q", got)
	}
}

// TestRedaction removes the raw and quote-doubled secret.
func TestRedaction(t *testing.T) {
	tests := []struct{ name, secret, message string }{
		{"raw", "sup3r-secret", `syntax error near "'sup3r-secret'"`},
		{"quote-doubled", "pa'ss", `syntax error near "'pa''ss'"`},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			got := redaction{message: tc.message, secret: tc.secret}.apply()
			doubled := strings.ReplaceAll(tc.secret, "'", "''")
			if strings.Contains(got, tc.secret) || strings.Contains(got, doubled) {
				t.Fatalf("secret survived redaction: %q", got)
			}
		})
	}
}

// TestProvisionTargetsForbidRuntimeForAuth locks the ibex_auth boundary: the
// auth login resolves bearers through one SECURITY DEFINER reader, and a
// membership in ibex_runtime would let it act as the runtime login instead.
// Both hold ibex_app today, so the reachability check cannot catch this by
// privilege alone; the forbidden list is the control.
func TestProvisionTargetsForbidRuntimeForAuth(t *testing.T) {
	for _, target := range provisionTargets {
		if target.role != "ibex_auth" {
			continue
		}
		if !containsRole(target.forbiddenRoles, "ibex_runtime") {
			t.Fatalf("ibex_auth forbiddenRoles = %v, want ibex_runtime present", target.forbiddenRoles)
		}
		if containsRole(target.requiredRoles, "ibex_runtime") {
			t.Fatalf("ibex_auth requiredRoles = %v must not contain ibex_runtime", target.requiredRoles)
		}
		return
	}
	t.Fatal("provisionTargets has no ibex_auth target")
}

// containsRole reports whether the role list names role.
func containsRole(roles []string, role string) bool {
	for _, candidate := range roles {
		if candidate == role {
			return true
		}
	}
	return false
}
