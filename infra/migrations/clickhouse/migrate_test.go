package clickhouse

import (
	"os"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"testing"
)

func TestMigrationFileNaming(t *testing.T) {
	entries, err := migrationFiles.ReadDir(".")
	if err != nil {
		t.Fatalf("read migrations: %v", err)
	}

	upPattern := regexp.MustCompile(`^(\d+)_(.+)\.up\.sql$`)
	var versions []int

	for _, e := range entries {
		if e.IsDir() {
			continue
		}
		name := e.Name()
		if !strings.HasSuffix(name, ".up.sql") {
			continue
		}
		m := upPattern.FindStringSubmatch(name)
		if m == nil {
			t.Errorf("invalid up migration filename: %s", name)
			continue
		}
		v, _ := strconv.Atoi(m[1])
		versions = append(versions, v)
		downName := m[1] + "_" + m[2] + ".down.sql"
		if _, err := migrationFiles.Open(downName); err != nil {
			t.Errorf("missing down migration for %s", name)
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

func TestNormalizeMigrateDSN(t *testing.T) {
	tests := []struct {
		in       string
		wantHost string
		wantMS   string
	}{
		{
			in:       "clickhouse://default:@localhost:9002/ibex",
			wantHost: "localhost:9002",
			wantMS:   "true",
		},
		{
			in:       "clickhouse://default:@localhost:8123/ibex",
			wantHost: "localhost:9002",
			wantMS:   "true",
		},
	}
	for _, tc := range tests {
		got := normalizeMigrateDSN(tc.in)
		if !strings.Contains(got, tc.wantHost) {
			t.Errorf("normalizeMigrateDSN(%q) host = %q, want %s", tc.in, got, tc.wantHost)
		}
		if !strings.Contains(got, "x-multi-statement="+tc.wantMS) {
			t.Errorf("normalizeMigrateDSN(%q) missing multi-statement: %q", tc.in, got)
		}
		if !strings.Contains(got, "database=ibex") {
			t.Errorf("normalizeMigrateDSN(%q) missing database: %q", tc.in, got)
		}
	}
}

func TestRedactedDSN(t *testing.T) {
	got := RedactedDSN("clickhouse://default:secret@localhost:9002?database=ibex")
	if strings.Contains(got, "secret") {
		t.Errorf("expected redacted password, got %q", got)
	}
}

func TestResolveDSN_prefersMigrateDSN(t *testing.T) {
	t.Setenv("CLICKHOUSE_MIGRATE_DSN", "clickhouse://a:b@ch:9002?database=ibex")
	t.Setenv("CLICKHOUSE_DSN", "clickhouse://x:y@other:8123/ibex")
	got := ResolveDSN()
	if !strings.Contains(got, "ch:9002") {
		t.Errorf("ResolveDSN() = %q", got)
	}
}

func TestResolveDSN_defaultWhenUnset(t *testing.T) {
	os.Unsetenv("CLICKHOUSE_MIGRATE_DSN")
	os.Unsetenv("CLICKHOUSE_DSN")
	got := ResolveDSN()
	if !strings.Contains(got, "localhost:9002") {
		t.Errorf("ResolveDSN() = %q, want default native port", got)
	}
}
