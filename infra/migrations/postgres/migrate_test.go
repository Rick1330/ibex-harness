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
	upPattern := regexp.MustCompile(`^(\d+)_(.+)\.up\.sql$`)
	var maxV int
	for _, e := range entries {
		if e.IsDir() {
			continue
		}
		m := upPattern.FindStringSubmatch(e.Name())
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

func TestMigrationFileNaming(t *testing.T) {
	entries, err := migrationFiles.ReadDir(".")
	if err != nil {
		t.Fatalf("read migrations: %v", err)
	}

	upPattern := regexp.MustCompile(`^(\d+)_(.+)\.up\.sql$`)
	var versions []int
	upFiles := make(map[int]string)

	for _, e := range entries {
		if e.IsDir() {
			continue
		}
		name := e.Name()
		if strings.HasSuffix(name, ".up.sql") {
			m := upPattern.FindStringSubmatch(name)
			if m == nil {
				t.Errorf("invalid up migration filename: %s", name)
				continue
			}
			v, _ := strconv.Atoi(m[1])
			versions = append(versions, v)
			upFiles[v] = m[2]

			downName := m[1] + "_" + m[2] + ".down.sql"
			if _, err := migrationFiles.Open(downName); err != nil {
				t.Errorf("missing down migration for %s", name)
			}
		}
	}

	if len(versions) == 0 {
		t.Fatal("no up migrations found")
	}

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
			want: "postgres://ibex:secret@localhost:5432/ibex?sslmode=disable&x-multi-statement=true",
		},
		{
			in:   "postgres://u:p@db.example.com:5432/mydb?sslmode=require",
			want: "postgres://u:p@db.example.com:5432/mydb?sslmode=require&x-multi-statement=true",
		},
	}
	for _, tc := range tests {
		got := normalizePostgresDSN(tc.in)
		if got != tc.want {
			t.Errorf("normalizePostgresDSN(%q) = %q, want %q", tc.in, got, tc.want)
		}
	}
}

func TestRedactedDSN(t *testing.T) {
	got := RedactedDSN("postgres://ibex:secret@localhost:5432/ibex?sslmode=disable")
	if strings.Contains(got, "secret") {
		t.Errorf("expected redacted password, got %q", got)
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
