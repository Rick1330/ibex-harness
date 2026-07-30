//go:build integration

package repository_test

import (
	"context"
	"database/sql"
	"errors"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/infra/testing/testutil"
	"github.com/Rick1330/ibex-harness/services/auth/internal/repository"
	"github.com/Rick1330/ibex-harness/services/auth/internal/token"
	"github.com/google/uuid"
)

func setupTokensRepo(t *testing.T) (*repository.TokensRepository, *sql.DB) {
	t.Helper()
	dsn, cleanupPG := testutil.SetupPostgres(t)
	t.Cleanup(cleanupPG)
	db := testutil.OpenDB(t, dsn)
	t.Cleanup(func() { _ = db.Close() })
	repo, err := repository.NewTokensRepository(db, nil)
	if err != nil {
		t.Fatalf("NewTokensRepository: %v", err)
	}
	return repo, db
}

type findActiveCase struct {
	name      string
	revoked   bool
	expired   bool
	wantFound bool
}

func seedFindActiveToken(t *testing.T, repo *repository.TokensRepository, db *sql.DB, tc findActiveCase) string {
	t.Helper()
	orgID := testutil.SeedOrganization(t, db, "Find Org "+tc.name, "find-"+uuid.NewString()[:8])
	tokenID := uuid.New()
	prefix := "ibex_pat_" + tokenID.String()
	bearer := prefix + "_findsecret"
	hash, err := token.HashForTest(bearer, token.DefaultArgon2Params())
	if err != nil {
		t.Fatalf("hash: %v", err)
	}
	var expiresAt *time.Time
	if tc.expired {
		past := time.Now().UTC().Add(-time.Hour)
		expiresAt = &past
	}
	if _, err = repo.InsertTestToken(context.Background(), orgID, prefix, hash, tc.name, 7, tc.revoked, expiresAt); err != nil {
		t.Fatalf("insert token: %v", err)
	}
	return prefix
}

func runFindActiveCase(t *testing.T, tc findActiveCase) {
	t.Helper()
	repo, db := setupTokensRepo(t)
	prefix := seedFindActiveToken(t, repo, db, tc)
	row, err := repo.FindActiveByPrefix(context.Background(), prefix)
	if tc.wantFound {
		if err != nil {
			t.Fatalf("FindActiveByPrefix: %v", err)
		}
		if row.Permissions != 7 {
			t.Fatalf("row perms: %d", row.Permissions)
		}
		return
	}
	if !errors.Is(err, sql.ErrNoRows) {
		t.Fatalf("expected sql.ErrNoRows, got %v", err)
	}
}

type listPageQuery struct {
	orgID      string
	cursor     string
	limit      int
	wantLen    int
	wantCursor bool
}

func listTokensPage(t *testing.T, repo *repository.TokensRepository, q listPageQuery) ([]repository.TokenMetadata, string) {
	t.Helper()
	rows, next, err := repo.ListTokens(context.Background(), q.orgID, q.cursor, q.limit)
	if err != nil {
		t.Fatalf("ListTokens: %v", err)
	}
	if len(rows) != q.wantLen {
		t.Fatalf("len: got %d want %d", len(rows), q.wantLen)
	}
	if q.wantCursor && next == "" {
		t.Fatal("expected next cursor")
	}
	if !q.wantCursor && next != "" {
		t.Fatalf("unexpected cursor %q", next)
	}
	return rows, next
}

func tokenIDsFromRows(rows []repository.TokenMetadata) map[string]bool {
	ids := make(map[string]bool, len(rows))
	for _, row := range rows {
		ids[row.ID] = true
	}
	return ids
}

func assertTokenIDsPresent(t *testing.T, want []string, rows []repository.TokenMetadata) {
	t.Helper()
	got := tokenIDsFromRows(rows)
	for _, id := range want {
		if !got[id] {
			t.Fatalf("missing token id %s", id)
		}
	}
}

func insertNamedToken(t *testing.T, repo *repository.TokensRepository, orgID, name string) string {
	t.Helper()
	tokenID := uuid.New()
	prefix := "ibex_pat_" + tokenID.String()
	bearer := prefix + "_" + name
	hash, err := token.HashForTest(bearer, token.DefaultArgon2Params())
	if err != nil {
		t.Fatalf("hash %s: %v", name, err)
	}
	id, err := repo.InsertTestToken(context.Background(), orgID, prefix, hash, name, 1, false, nil)
	if err != nil {
		t.Fatalf("insert %s: %v", name, err)
	}
	return id
}

type agentsScenario struct {
	DB      *sql.DB
	Repo    *repository.AgentsRepository
	OrgA    string
	OrgB    string
	UserA   string
	AgentID string
}

func withAgentsScenario(t *testing.T, status string, crossOrg bool, fn func(t *testing.T, s agentsScenario, lookupOrg string)) {
	t.Helper()
	dsn, cleanupPG := testutil.SetupPostgres(t)
	t.Cleanup(cleanupPG)

	db := testutil.OpenDB(t, dsn)
	t.Cleanup(func() { _ = db.Close() })

	repo := repository.NewAgentsRepository(db, nil)
	label := uuid.NewString()[:8]
	orgA := testutil.SeedOrganization(t, db, "Org A "+label, "org-a-"+label)
	orgB := testutil.SeedOrganization(t, db, "Org B "+label, "org-b-"+label)
	userA := testutil.SeedUser(t, db, orgA, "user-"+label+"@test.local", "User A")
	agentID := testutil.SeedAgentWithStatus(t, db, orgA, userA, "Agent "+label, "agent-"+label, status)

	lookupOrg := orgA
	if crossOrg {
		lookupOrg = orgB
	}

	fn(t, agentsScenario{DB: db, Repo: repo, OrgA: orgA, OrgB: orgB, UserA: userA, AgentID: agentID}, lookupOrg)
}

func (s agentsScenario) lookupAgent(t *testing.T, lookupOrg string) *repository.AgentRecord {
	t.Helper()
	rec, err := s.Repo.GetByIDAndOrg(context.Background(), uuid.MustParse(s.AgentID), uuid.MustParse(lookupOrg))
	if err != nil {
		t.Fatalf("GetByIDAndOrg: %v", err)
	}
	return rec
}
