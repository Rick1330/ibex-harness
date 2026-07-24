//go:build integration

package postgres

import (
	"context"
	"database/sql"
	"testing"
)

func TestRLSDirectivesIsolation(t *testing.T) {
	dsn := testDSN()
	db := openTestDB(t)
	defer db.Close()
	resetSchema(t, db)
	if err := Up(dsn); err != nil {
		t.Fatalf("up: %v", err)
	}

	ctx := context.Background()
	orgA, orgB := seedTwoOrgsWithAgents(t, ctx, db)
	seedDirectiveForOrg(t, ctx, directiveSeed{db: db, orgID: orgA, agentSlug: "agent-a", content: "directive-a"})
	seedDirectiveForOrg(t, ctx, directiveSeed{db: db, orgID: orgB, agentSlug: "agent-b", content: "directive-b"})

	assertTableCount(t, ctx, tableCountCheck{db: db, table: "directives", orgID: "", want: 0})
	assertTableCount(t, ctx, tableCountCheck{db: db, table: "directives", orgID: orgA, want: 1})
	assertTableCount(t, ctx, tableCountCheck{db: db, table: "directives", orgID: orgB, want: 1})
	assertTableCount(t, ctx, tableCountCheck{db: db, table: "directive_versions", orgID: "", want: 0})
	assertTableCount(t, ctx, tableCountCheck{db: db, table: "directive_versions", orgID: orgA, want: 1})
	assertTableCount(t, ctx, tableCountCheck{db: db, table: "directive_versions", orgID: orgB, want: 1})
}

func TestDirectiveVersionsAppendOnly(t *testing.T) {
	dsn := testDSN()
	db := openTestDB(t)
	defer db.Close()
	resetSchema(t, db)
	if err := Up(dsn); err != nil {
		t.Fatalf("up: %v", err)
	}

	ctx := context.Background()
	orgA, _ := seedTwoOrgsWithAgents(t, ctx, db)
	seedDirectiveForOrg(t, ctx, directiveSeed{db: db, orgID: orgA, agentSlug: "agent-a", content: "v1"})

	err := withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(ctx, `UPDATE ibex_core.directive_versions SET content = 'mutated'`)
		return err
	})
	if err == nil {
		t.Fatal("expected append-only update to fail")
	}

	err = withAppRole(ctx, db, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(ctx, `DELETE FROM ibex_core.directive_versions`)
		return err
	})
	if err == nil {
		t.Fatal("expected ibex_app DELETE on directive_versions to fail")
	}
}

func TestDirectiveActiveVersionOwnership(t *testing.T) {
	dsn := testDSN()
	db := openTestDB(t)
	defer db.Close()
	resetSchema(t, db)
	if err := Up(dsn); err != nil {
		t.Fatalf("up: %v", err)
	}

	ctx := context.Background()
	orgA, orgB := seedTwoOrgsWithAgents(t, ctx, db)
	a := seedDirectiveForOrg(t, ctx, directiveSeed{db: db, orgID: orgA, agentSlug: "agent-a", content: "a-v1"})
	b := seedDirectiveForOrg(t, ctx, directiveSeed{db: db, orgID: orgB, agentSlug: "agent-b", content: "b-v1"})
	a2 := insertSecondVersion(t, ctx, db, versionSeed{orgID: orgA, directiveID: a.directiveID, content: "a-v2"})
	other := seedSecondAgentDirective(t, ctx, db, orgA)

	assertActiveVersionUpdateFails(t, ctx, activeVersionPoint{db: db, directiveID: a.directiveID, versionID: b.versionID})
	assertActiveVersionUpdateFails(t, ctx, activeVersionPoint{db: db, directiveID: a.directiveID, versionID: other.versionID})
	assertActiveVersionUpdateOK(t, ctx, activeVersionPoint{db: db, directiveID: a.directiveID, versionID: a.versionID})
	assertActiveVersionUpdateOK(t, ctx, activeVersionPoint{db: db, directiveID: a.directiveID, versionID: a2})
}

func TestDirectiveDeleteCascadesVersions(t *testing.T) {
	dsn := testDSN()
	db := openTestDB(t)
	defer db.Close()
	resetSchema(t, db)
	if err := Up(dsn); err != nil {
		t.Fatalf("up: %v", err)
	}

	ctx := context.Background()
	orgA, _ := seedTwoOrgsWithAgents(t, ctx, db)
	seeded := seedDirectiveForOrg(t, ctx, directiveSeed{db: db, orgID: orgA, agentSlug: "agent-a", content: "cascade-v1"})

	err := withAppRole(ctx, db, func(tx *sql.Tx) error {
		if _, err := tx.ExecContext(ctx, `SELECT set_config('app.current_org_id', $1, true)`, orgA); err != nil {
			return err
		}
		_, err := tx.ExecContext(ctx, `DELETE FROM ibex_core.directives WHERE id = $1::uuid`, seeded.directiveID)
		return err
	})
	if err != nil {
		t.Fatalf("ibex_app delete directive: %v", err)
	}

	assertTableCount(t, ctx, tableCountCheck{db: db, table: "directives", orgID: orgA, want: 0})
	assertTableCount(t, ctx, tableCountCheck{db: db, table: "directive_versions", orgID: orgA, want: 0})
}

type versionSeed struct {
	orgID, directiveID, content string
}

type activeVersionPoint struct {
	db                     *sql.DB
	directiveID, versionID string
}

const insertDirectiveVersionV2SQL = `
	INSERT INTO ibex_core.directive_versions
		(directive_id, org_id, version_num, content, content_hash)
	VALUES ($1::uuid, $2::uuid, 2, $3, $4)
	RETURNING id::text`

const updateActiveVersionSQL = `
	UPDATE ibex_core.directives
	SET active_version_id = $1::uuid
	WHERE id = $2::uuid`

func insertSecondVersion(t *testing.T, ctx context.Context, db *sql.DB, seed versionSeed) string {
	t.Helper()
	var versionID string
	contentHash := "hash-" + seed.content
	err := withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		return tx.QueryRowContext(ctx, insertDirectiveVersionV2SQL,
			seed.directiveID, seed.orgID, seed.content, contentHash).Scan(&versionID)
	})
	if err != nil {
		t.Fatalf("insert second version: %v", err)
	}
	return versionID
}

func seedSecondAgentDirective(t *testing.T, ctx context.Context, db *sql.DB, orgID string) seededDirective {
	t.Helper()
	err := withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		return insertUserAndAgent(ctx, tx, orgID, userAgentSeed{
			email: "user-a2@example.com", name: "User A2", agent: "Agent A2", slug: "agent-a2",
		})
	})
	if err != nil {
		t.Fatalf("seed second agent: %v", err)
	}
	return seedDirectiveForOrg(t, ctx, directiveSeed{db: db, orgID: orgID, agentSlug: "agent-a2", content: "a2-v1"})
}

func assertActiveVersionUpdateFails(t *testing.T, ctx context.Context, point activeVersionPoint) {
	t.Helper()
	err := withServiceAccount(ctx, point.db, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(ctx, updateActiveVersionSQL, point.versionID, point.directiveID)
		return err
	})
	if err == nil {
		t.Fatal("expected active_version ownership check to fail")
	}
}

func assertActiveVersionUpdateOK(t *testing.T, ctx context.Context, point activeVersionPoint) {
	t.Helper()
	err := withServiceAccount(ctx, point.db, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(ctx, updateActiveVersionSQL, point.versionID, point.directiveID)
		return err
	})
	if err != nil {
		t.Fatalf("expected active_version update to succeed: %v", err)
	}
}
