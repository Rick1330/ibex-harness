//go:build integration

package auth_test

import (
	"context"
	"path/filepath"
	"runtime"
	"sync"
	"testing"

	"github.com/Rick1330/ibex-harness/infra/testing/testutil"
	"github.com/Rick1330/ibex-harness/packages/permissions"
	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
)

const (
	devSeedOrgID = "00000000-0000-0000-0000-000000000001"
	devSeedPAT   = "ibex_pat_00000000-0000-0000-0000-000000000004_LOCALDEVELOPMENTONLY"
	devSeedAgent = "00000000-0000-0000-0000-000000000003"
)

// Fixed seed IDs are shared across tests; serialize seed SQL on the compose-test DB.
var seedDevSQLMu sync.Mutex

var devSeedExpectedCounts = map[string]int{
	"organizations": 1,
	"users":         1,
	"agents":        1,
	"tokens":        1,
}

func TestSeedScript_Idempotent(t *testing.T) {
	t.Parallel()
	dsn, cleanupPG := testutil.SetupPostgres(t)
	defer cleanupPG()

	runSeedDevSQL(t, dsn)
	afterFirst := seedRowCounts(t, dsn)
	assertDevSeedCounts(t, afterFirst)

	runSeedDevSQL(t, dsn)
	assertSeedCountsUnchanged(t, afterFirst, seedRowCounts(t, dsn))
}

func assertSeedCountsUnchanged(t *testing.T, before, after map[string]int) {
	t.Helper()
	for table, want := range before {
		if got := after[table]; got != want {
			t.Fatalf("%s count changed after second seed: %d -> %d", table, want, got)
		}
	}
}

func assertDevSeedCounts(t *testing.T, counts map[string]int) {
	t.Helper()
	for table, want := range devSeedExpectedCounts {
		if got := counts[table]; got != want {
			t.Fatalf("%s: got %d rows, want %d (counts=%+v)", table, got, want, counts)
		}
	}
}

func TestSeedPAT_Validates(t *testing.T) {
	t.Parallel()
	dsn, cleanupPG := testutil.SetupPostgres(t)
	defer cleanupPG()

	runSeedDevSQL(t, dsn)

	client, cleanup := startAuthGRPC(t, dsn)
	defer cleanup()

	resp, err := client.ValidateToken(context.Background(), &authv1.ValidateTokenRequest{
		AccessToken: devSeedPAT,
	})
	if err != nil {
		t.Fatalf("ValidateToken: %v", err)
	}
	if resp.GetOrgId() != devSeedOrgID {
		t.Fatalf("org_id: got %q want %s", resp.GetOrgId(), devSeedOrgID)
	}
	if !permissions.Has(resp.GetPermissions(), permissions.ProxyChatCompletion) {
		t.Fatalf("permissions missing ProxyChatCompletion: %d", resp.GetPermissions())
	}
	if resp.GetAgentId() != devSeedAgent {
		t.Fatalf("agent_id: got %q want %s", resp.GetAgentId(), devSeedAgent)
	}
}

func runSeedDevSQL(t *testing.T, dsn string) {
	t.Helper()
	seedDevSQLMu.Lock()
	defer seedDevSQLMu.Unlock()
	seedPath := filepath.Join(repoRoot(t), "infra", "scripts", "seed_dev.sql")
	testutil.ExecSQLFile(t, dsn, seedPath)
}

func seedRowCounts(t *testing.T, dsn string) map[string]int {
	t.Helper()
	db := testutil.OpenDB(t, dsn)
	defer db.Close()
	ctx := context.Background()
	queries := map[string]string{
		"organizations": "SELECT COUNT(*) FROM ibex_core.organizations WHERE id = '00000000-0000-0000-0000-000000000001'",
		"users":         "SELECT COUNT(*) FROM ibex_core.users WHERE id = '00000000-0000-0000-0000-000000000002'",
		"agents":        "SELECT COUNT(*) FROM ibex_core.agents WHERE id = '00000000-0000-0000-0000-000000000003'",
		"tokens":        "SELECT COUNT(*) FROM ibex_core.tokens WHERE id = '00000000-0000-0000-0000-000000000004'",
	}
	counts := map[string]int{}
	for table, q := range queries {
		var n int
		if err := db.QueryRowContext(ctx, q).Scan(&n); err != nil {
			t.Fatalf("count %s: %v", table, err)
		}
		counts[table] = n
	}
	return counts
}

func repoRoot(t *testing.T) string {
	t.Helper()
	_, file, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("runtime.Caller failed")
	}
	return filepath.Clean(filepath.Join(filepath.Dir(file), "..", ".."))
}
