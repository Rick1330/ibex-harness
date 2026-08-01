package clickhouse

import (
	"io/fs"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"testing"
)

func TestUnit_Migrations_Naming(t *testing.T) {
	t.Parallel()
	entries, err := migrationFiles.ReadDir(".")
	if err != nil {
		t.Fatalf("read migrations: %v", err)
	}
	versions := collectUpVersions(t, entries)
	if len(versions) == 0 {
		t.Fatal("no up migrations found")
	}
	assertStrictlyIncreasing(t, versions)
}

func collectUpVersions(t *testing.T, entries []fs.DirEntry) []int {
	t.Helper()
	upPattern := regexp.MustCompile(`^(\d{6})_(.+)\.up\.sql$`)
	var versions []int
	for _, e := range entries {
		if e.IsDir() || !strings.HasSuffix(e.Name(), ".up.sql") {
			continue
		}
		m := upPattern.FindStringSubmatch(e.Name())
		if m == nil {
			t.Errorf("invalid up migration filename: %s", e.Name())
			continue
		}
		v, _ := strconv.Atoi(m[1])
		versions = append(versions, v)
		assertDownExists(t, m[1]+"_"+m[2]+".down.sql")
	}
	return versions
}

func assertDownExists(t *testing.T, downName string) {
	t.Helper()
	if _, err := fs.Stat(migrationFiles, downName); err != nil {
		t.Errorf("missing down migration: %s", downName)
	}
}

func assertStrictlyIncreasing(t *testing.T, versions []int) {
	t.Helper()
	sort.Ints(versions)
	for i := 1; i < len(versions); i++ {
		if versions[i] <= versions[i-1] {
			t.Errorf("migration versions not strictly increasing: %d then %d", versions[i-1], versions[i])
		}
	}
}

func TestUnit_MigrateDSN_Normalize(t *testing.T) {
	t.Parallel()
	cases := []struct {
		in, wantHost string
	}{
		{in: "clickhouse://default:@localhost:9002/ibex", wantHost: "localhost:9002"},
		{in: "clickhouse://default:@localhost:8123/ibex", wantHost: "localhost:9002"},
		{in: "clickhouse://default:@ch.example.com:8123/ibex", wantHost: "ch.example.com:8123"},
	}
	for _, tc := range cases {
		got := ParseConn(tc.in).String()
		if !strings.Contains(got, tc.wantHost) {
			t.Errorf("ParseConn(%q) = %q, want host %s", tc.in, got, tc.wantHost)
		}
		if !strings.Contains(got, "x-multi-statement=true") || !strings.Contains(got, "database=ibex") {
			t.Errorf("ParseConn(%q) missing query defaults: %q", tc.in, got)
		}
	}
}

func TestUnit_MigrateDSN_Redacted(t *testing.T) {
	t.Parallel()
	got := ParseConn("clickhouse://default:secret@localhost:9002?database=ibex").Redacted()
	if strings.Contains(got, "secret") {
		t.Errorf("expected password stripped, got %q", got)
	}
}

func TestUnit_MigrateDSN_FlattensPasswordToQuery(t *testing.T) {
	t.Parallel()
	got := ParseConn("clickhouse://default:ibexdev@localhost:9002?database=ibex").String()
	if strings.Contains(got, "ibexdev@") {
		t.Fatalf("userinfo password should be flattened: %q", got)
	}
	if !strings.Contains(got, "password=ibexdev") || !strings.Contains(got, "username=default") {
		t.Fatalf("want username/password query: %q", got)
	}
}

func TestUnit_MigrateDSN_PrefersMigrateEnv(t *testing.T) {
	t.Setenv("CLICKHOUSE_MIGRATE_DSN", "clickhouse://a:b@ch:9002?database=ibex")
	t.Setenv("CLICKHOUSE_DSN", "clickhouse://x:y@other:8123/ibex")
	got := ResolveDSN()
	if !strings.Contains(got, "ch:9002") {
		t.Errorf("ResolveDSN() = %q", got)
	}
}

func TestUnit_MigrateDSN_DefaultWhenUnset(t *testing.T) {
	t.Setenv("CLICKHOUSE_MIGRATE_DSN", "")
	t.Setenv("CLICKHOUSE_DSN", "")
	got := ResolveDSN()
	if !strings.Contains(got, "localhost:9002") {
		t.Errorf("ResolveDSN() = %q, want default native port", got)
	}
}
