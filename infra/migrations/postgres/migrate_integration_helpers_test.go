//go:build integration

package postgres

import (
	"context"
	"database/sql"
	"fmt"
	"testing"
)

const insertDirectiveVersionSQL = `
	INSERT INTO ibex_core.directive_versions
		(directive_id, org_id, version_num, content, content_hash)
	VALUES ($1::uuid, $2::uuid, 1, $3, $4)
	RETURNING id::text`

type userAgentSeed struct {
	email, name, agent, slug string
}

type tableCountCheck struct {
	db    *sql.DB
	table string
	orgID string
	want  int
}

type directiveSeed struct {
	db                        *sql.DB
	orgID, agentSlug, content string
}

type seededDirective struct {
	directiveID string
	versionID   string
}

func seedTwoOrgsWithAgents(t *testing.T, ctx context.Context, db *sql.DB) (orgA, orgB string) {
	t.Helper()
	err := withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		var err error
		orgA, err = insertOrg(ctx, tx, "Org A", "org-a")
		if err != nil {
			return err
		}
		orgB, err = insertOrg(ctx, tx, "Org B", "org-b")
		if err != nil {
			return err
		}
		if err := insertUserAndAgent(ctx, tx, orgA, userAgentSeed{
			email: "user-a@example.com", name: "User A", agent: "Agent A", slug: "agent-a",
		}); err != nil {
			return err
		}
		return insertUserAndAgent(ctx, tx, orgB, userAgentSeed{
			email: "user-b@example.com", name: "User B", agent: "Agent B", slug: "agent-b",
		})
	})
	if err != nil {
		t.Fatalf("seed: %v", err)
	}
	return orgA, orgB
}

func insertOrg(ctx context.Context, tx *sql.Tx, name, slug string) (string, error) {
	var id string
	err := tx.QueryRowContext(ctx, `
		INSERT INTO ibex_core.organizations (name, slug)
		VALUES ($1, $2) RETURNING id::text`, name, slug).Scan(&id)
	return id, err
}

func insertUserAndAgent(ctx context.Context, tx *sql.Tx, orgID string, seed userAgentSeed) error {
	var userID string
	if err := tx.QueryRowContext(ctx, `
		INSERT INTO ibex_core.users (org_id, email, name)
		VALUES ($1::uuid, $2, $3)
		RETURNING id::text`, orgID, seed.email, seed.name).Scan(&userID); err != nil {
		return err
	}
	_, err := tx.ExecContext(ctx, `
		INSERT INTO ibex_core.agents (org_id, created_by, name, slug)
		VALUES ($1::uuid, $2::uuid, $3, $4)`, orgID, userID, seed.agent, seed.slug)
	return err
}

func assertTableCount(t *testing.T, ctx context.Context, check tableCountCheck) {
	t.Helper()
	q, ok := ibexCoreCountQuery(check.table)
	if !ok {
		t.Fatalf("unsupported table %q", check.table)
	}
	var count int
	err := withAppRole(ctx, check.db, func(tx *sql.Tx) error {
		if check.orgID != "" {
			if _, err := tx.ExecContext(ctx, `SELECT set_config('app.current_org_id', $1, true)`, check.orgID); err != nil {
				return err
			}
		}
		return tx.QueryRowContext(ctx, q).Scan(&count)
	})
	if err != nil {
		t.Fatalf("count %s (org=%q): %v", check.table, check.orgID, err)
	}
	if count != check.want {
		t.Fatalf("expected %d %s (org=%q), got %d", check.want, check.table, check.orgID, count)
	}
}

func ibexCoreCountQuery(table string) (string, bool) {
	switch table {
	case "agents":
		return `SELECT COUNT(*) FROM ibex_core.agents`, true
	case "directives":
		return `SELECT COUNT(*) FROM ibex_core.directives`, true
	case "directive_versions":
		return `SELECT COUNT(*) FROM ibex_core.directive_versions`, true
	case "sessions":
		return `SELECT COUNT(*) FROM ibex_core.sessions`, true
	case "checkpoints":
		return `SELECT COUNT(*) FROM ibex_core.checkpoints`, true
	case "memories":
		return `SELECT COUNT(*) FROM ibex_core.memories`, true
	case "memory_labels":
		return `SELECT COUNT(*) FROM ibex_core.memory_labels`, true
	default:
		return "", false
	}
}

func seedDirectiveForOrg(t *testing.T, ctx context.Context, seed directiveSeed) seededDirective {
	t.Helper()
	var out seededDirective
	err := withServiceAccount(ctx, seed.db, func(tx *sql.Tx) error {
		var agentID string
		if err := tx.QueryRowContext(ctx, `
			SELECT id::text FROM ibex_core.agents
			WHERE org_id = $1::uuid AND slug = $2`, seed.orgID, seed.agentSlug).Scan(&agentID); err != nil {
			return err
		}
		if err := tx.QueryRowContext(ctx, `
			INSERT INTO ibex_core.directives (org_id, agent_id)
			VALUES ($1::uuid, $2::uuid) RETURNING id::text`, seed.orgID, agentID).Scan(&out.directiveID); err != nil {
			return err
		}
		contentHash := "hash-" + seed.content
		if err := tx.QueryRowContext(ctx, insertDirectiveVersionSQL,
			out.directiveID, seed.orgID, seed.content, contentHash).Scan(&out.versionID); err != nil {
			return err
		}
		return activateDirectiveVersion(ctx, tx, activateVersionArgs{
			orgID: seed.orgID, directiveID: out.directiveID, versionID: out.versionID,
		})
	})
	if err != nil {
		t.Fatalf("seed directive org=%s: %v", seed.orgID, err)
	}
	return out
}

const activateDirectiveVersionSQL = `
	UPDATE ibex_core.directives
	SET active_version_id = $1::uuid
	WHERE id = $2::uuid AND org_id = $3::uuid`

type activateVersionArgs struct {
	orgID, directiveID, versionID string
}

func activateDirectiveVersion(ctx context.Context, tx *sql.Tx, args activateVersionArgs) error {
	res, err := tx.ExecContext(ctx, activateDirectiveVersionSQL, args.versionID, args.directiveID, args.orgID)
	if err != nil {
		return fmt.Errorf("activate directive version: %w", err)
	}
	n, err := res.RowsAffected()
	if err != nil {
		return fmt.Errorf("activate directive version rows: %w", err)
	}
	if n != 1 {
		return fmt.Errorf("activate directive version: affected %d rows, want 1", n)
	}
	return nil
}

func assertCoreTablesExist(t *testing.T, ctx context.Context, db *sql.DB, tables []string) {
	t.Helper()
	for _, table := range tables {
		assertCoreTableExists(t, ctx, db, table)
	}
}

func assertCoreTableExists(t *testing.T, ctx context.Context, db *sql.DB, table string) {
	t.Helper()
	var exists bool
	err := db.QueryRowContext(ctx, `
		SELECT EXISTS (
			SELECT 1 FROM information_schema.tables
			WHERE table_schema = 'ibex_core' AND table_name = $1
		)`, table).Scan(&exists)
	if err != nil {
		t.Fatalf("check table %s: %v", table, err)
	}
	if !exists {
		t.Errorf("missing table ibex_core.%s", table)
	}
}

func assertCoreTablesRLSEnabled(t *testing.T, ctx context.Context, db *sql.DB, tables []string) {
	t.Helper()
	for _, table := range tables {
		assertCoreTableRLSEnabled(t, ctx, db, table)
	}
}

func assertCoreTableRLSEnabled(t *testing.T, ctx context.Context, db *sql.DB, table string) {
	t.Helper()
	var rls bool
	err := db.QueryRowContext(ctx, `
		SELECT c.relrowsecurity
		FROM pg_class c
		JOIN pg_namespace n ON n.oid = c.relnamespace
		WHERE n.nspname = 'ibex_core' AND c.relname = $1`, table).Scan(&rls)
	if err != nil {
		t.Fatalf("check rls %s: %v", table, err)
	}
	if !rls {
		t.Errorf("RLS not enabled on ibex_core.%s", table)
	}
}

func assertCoreTableForceRLS(t *testing.T, ctx context.Context, db *sql.DB, table string) {
	t.Helper()
	var forced bool
	err := db.QueryRowContext(ctx, `
		SELECT c.relforcerowsecurity
		FROM pg_class c
		JOIN pg_namespace n ON n.oid = c.relnamespace
		WHERE n.nspname = 'ibex_core' AND c.relname = $1`, table).Scan(&forced)
	if err != nil {
		t.Fatalf("force rls %s: %v", table, err)
	}
	if !forced {
		t.Errorf("expected FORCE ROW LEVEL SECURITY on ibex_core.%s", table)
	}
}
