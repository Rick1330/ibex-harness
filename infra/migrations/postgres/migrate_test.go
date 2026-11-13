package postgres

import (
	"os"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"testing"
)

func maxEmbeddedMigrationVersion(t *testing.T) uint {
	t.Helper()
	entries, err := migrationFiles.ReadDir(".")
	if err != nil {
		t.Fatalf("read migrations: %v", err)
	}
	var maxV int
	for _, e := range entries {
		if e.IsDir() {
			continue
		}
		m := upMigrationPattern.FindStringSubmatch(e.Name())
		if m == nil {
			continue
		}
		v, _ := strconv.Atoi(m[1])
		if v > maxV {
			maxV = v
		}
	}
	if maxV == 0 {
		t.Fatal("no up migrations found")
	}
	return uint(maxV)
}

// upMigrationPattern is the naming contract for an up migration: a numeric
// version, an underscore, a description, and the .up.sql suffix.
var upMigrationPattern = regexp.MustCompile(`^(\d+)_(.+)\.up\.sql$`)

func TestMigrationFileNaming(t *testing.T) {
	entries, err := migrationFiles.ReadDir(".")
	if err != nil {
		t.Fatalf("read migrations: %v", err)
	}

	versions := collectMigrationVersions(t, entries)
	if len(versions) == 0 {
		t.Fatal("no up migrations found")
	}

	assertVersionsStrictlyIncrease(t, versions)
}

// collectMigrationVersions returns the version of every up migration in
// entries, in directory order.
func collectMigrationVersions(t *testing.T, entries []os.DirEntry) []int {
	t.Helper()
	var versions []int
	for _, e := range entries {
		if e.IsDir() || !strings.HasSuffix(e.Name(), ".up.sql") {
			continue
		}
		if version, ok := upMigrationVersion(t, e.Name()); ok {
			versions = append(versions, version)
		}
	}
	return versions
}

// upMigrationVersion parses one up-migration filename into its version. It
// reports a name that breaks the contract and a missing down migration, and
// returns ok=false when the name does not parse.
func upMigrationVersion(t *testing.T, name string) (int, bool) {
	t.Helper()
	m := upMigrationPattern.FindStringSubmatch(name)
	if m == nil {
		t.Errorf("invalid up migration filename: %s", name)
		return 0, false
	}
	if _, err := migrationFiles.Open(m[1] + "_" + m[2] + ".down.sql"); err != nil {
		t.Errorf("missing down migration for %s", name)
	}
	version, _ := strconv.Atoi(m[1])
	return version, true
}

// assertVersionsStrictlyIncrease requires every migration version to be greater
// than the one before it, which also rules out a duplicate version.
func assertVersionsStrictlyIncrease(t *testing.T, versions []int) {
	t.Helper()
	sort.Ints(versions)
	for i := 1; i < len(versions); i++ {
		if versions[i] <= versions[i-1] {
			t.Errorf("migration versions not strictly increasing: %d then %d", versions[i-1], versions[i])
		}
	}
}

func TestNormalizePostgresDSN(t *testing.T) {
	tests := []struct {
		in   string
		want string
	}{
		{
			in:   "postgresql+asyncpg://ibex:secret@localhost:5432/ibex",
			want: "postgres://ibex:secret@localhost:5432/ibex?sslmode=disable",
		},
		{
			in:   "postgres://u:p@db.example.com:5432/mydb?sslmode=require",
			want: "postgres://u:p@db.example.com:5432/mydb?sslmode=require",
		},
	}
	for _, tc := range tests {
		got := normalizePostgresDSN(tc.in)
		if got != tc.want {
			t.Errorf("normalizePostgresDSN(%q) = %q, want %q", tc.in, got, tc.want)
		}
	}
}

// redactedDSNCase is one RedactedDSN fixture: the substrings that must not
// survive redaction, and the substrings that must.
type redactedDSNCase struct {
	name string
	dsn  string
	gone []string
	kept []string
}

func TestRedactedDSN(t *testing.T) {
	for _, tc := range redactedDSNCases() {
		t.Run(tc.name, func(t *testing.T) {
			assertRedactedDSN(t, tc)
		})
	}
}

// assertRedactedDSN requires every credential substring to be masked and every
// non-credential substring, including the sslmode the caller asked for, to
// survive redaction.
func assertRedactedDSN(t *testing.T, tc redactedDSNCase) {
	t.Helper()
	got := RedactedDSN(tc.dsn)
	assertMasked(t, tc, got)
	assertKept(t, tc, got)
}

// assertMasked reports every credential substring that still appears in the
// redacted DSN.
func assertMasked(t *testing.T, tc redactedDSNCase, got string) {
	t.Helper()
	for _, want := range tc.gone {
		if strings.Contains(got, want) {
			t.Errorf("RedactedDSN(%q) = %q, want %q masked", tc.dsn, got, want)
		}
	}
}

// assertKept reports every substring that redaction dropped by mistake.
func assertKept(t *testing.T, tc redactedDSNCase, got string) {
	t.Helper()
	for _, want := range tc.kept {
		if !strings.Contains(got, want) {
			t.Errorf("RedactedDSN(%q) = %q, want %q kept", tc.dsn, got, want)
		}
	}
}

// redactedDSNCases are the credential shapes RedactedDSN must handle: a
// userinfo password, a query-string password, and a query-string passfile. Each
// case also pins that the requested sslmode survives, because a redaction that
// drops it silently weakens the connection.
func redactedDSNCases() []redactedDSNCase {
	return []redactedDSNCase{
		{
			name: "userinfo password",
			dsn:  "postgres://ibex:secret@localhost:5432/ibex?sslmode=disable",
			gone: []string{"secret"},
			kept: []string{"ibex:", "localhost:5432/ibex", "sslmode=disable"},
		},
		{
			// lib/pq and pgx both read a password from the query string, so a
			// redaction that only touches the userinfo leaks it into the log.
			name: "query password",
			dsn:  "postgres://ibex@localhost:5432/ibex?password=secret&sslmode=require",
			gone: []string{"secret"},
			kept: []string{"password=REDACTED", "sslmode=require"},
		},
		{
			// A passfile is a path to a credential, so the path is a credential.
			name: "query passfile",
			dsn:  "postgres://ibex@localhost:5432/ibex?passfile=%2Fhome%2Fibex%2F.pgpass&sslmode=verify-full",
			gone: []string{"pgpass", "home"},
			kept: []string{"passfile=REDACTED", "sslmode=verify-full"},
		},
	}
}

func TestResolveDSN_prefersMigrateDSN(t *testing.T) {
	t.Setenv("POSTGRES_MIGRATE_DSN", "postgres://a:b@host:5432/db?sslmode=disable")
	t.Setenv("POSTGRES_DSN", "postgresql+asyncpg://x:y@other:5432/other")
	got := ResolveDSN()
	if !strings.HasPrefix(got, "postgres://a:b@host:5432/db") {
		t.Errorf("ResolveDSN() = %q", got)
	}
}

func TestResolveDSN_defaultWhenUnset(t *testing.T) {
	os.Unsetenv("POSTGRES_MIGRATE_DSN")
	os.Unsetenv("POSTGRES_DSN")
	got := ResolveDSN()
	if got != defaultMigrateDSN {
		t.Errorf("ResolveDSN() = %q, want default", got)
	}
}
