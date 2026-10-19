//go:build integration

package postgres

import (
	"context"
	"database/sql"
	"strings"
	"testing"

	"github.com/google/uuid"
)

const relayFenceFn = "ibex_core.evidence_outbox_check_session_fence"

type relayFenceFixture struct {
	db        *sql.DB
	ctx       context.Context
	dsn       string
	orgID     string
	otherOrg  string
	sessionID string
}

func newRelayFenceFixture(t *testing.T) *relayFenceFixture {
	t.Helper()
	dsn := testDSN()
	db := openTestDB(t)
	t.Cleanup(func() { _ = db.Close() })
	resetSchema(t, db)
	if err := Up(dsn); err != nil {
		t.Fatalf("up: %v", err)
	}
	f := &relayFenceFixture{db: db, ctx: context.Background(), dsn: dsn}
	f.orgID, f.sessionID = seedRelayFenceOrgWithSession(t, f.ctx, db, "relay-fence-a")
	f.otherOrg, _ = seedRelayFenceOrgWithSession(t, f.ctx, db, "relay-fence-b")
	return f
}

func seedRelayFenceOrgWithSession(t *testing.T, ctx context.Context, db *sql.DB, slug string) (string, string) {
	t.Helper()
	var orgID, sessionID string
	err := withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		var err error
		orgID, err = insertOrg(ctx, tx, "Org "+slug, slug)
		if err != nil {
			return err
		}
		var userID string
		if err := tx.QueryRowContext(ctx, `
			INSERT INTO ibex_core.users (org_id, email, name)
			VALUES ($1::uuid, $2, $3) RETURNING id::text`,
			orgID, uuid.NewString()+"@example.com", "Fence User").Scan(&userID); err != nil {
			return err
		}
		var agentID string
		if err := tx.QueryRowContext(ctx, `
			INSERT INTO ibex_core.agents (org_id, created_by, name, slug)
			VALUES ($1::uuid, $2::uuid, $3, $4) RETURNING id::text`,
			orgID, userID, "Fence Agent", uuid.NewString()[:8]).Scan(&agentID); err != nil {
			return err
		}
		return tx.QueryRowContext(ctx, `
			INSERT INTO ibex_core.sessions (org_id, agent_id, model, provider)
			VALUES ($1::uuid, $2::uuid, 'gpt-4o', 'openai') RETURNING id::text`,
			orgID, agentID).Scan(&sessionID)
	})
	if err != nil {
		t.Fatalf("seed org with session: %v", err)
	}
	return orgID, sessionID
}

func (f *relayFenceFixture) checkFence(t *testing.T, orgID, resourceID string, version int64) string {
	t.Helper()
	var out string
	if err := f.db.QueryRowContext(f.ctx,
		`SELECT `+relayFenceFn+`($1::uuid, $2::uuid, $3)`, orgID, resourceID, version,
	).Scan(&out); err != nil {
		t.Fatalf("check fence: %v", err)
	}
	return out
}

func (f *relayFenceFixture) softDeleteSession(t *testing.T) {
	t.Helper()
	err := withServiceAccount(f.ctx, f.db, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(f.ctx,
			`UPDATE ibex_core.sessions SET deleted_at = NOW() WHERE id = $1::uuid`, f.sessionID)
		return err
	})
	if err != nil {
		t.Fatalf("soft delete session: %v", err)
	}
}

func (f *relayFenceFixture) sessionFenceVersion(t *testing.T) int64 {
	t.Helper()
	var v int64
	if err := f.db.QueryRowContext(f.ctx,
		`SELECT evidence_fence_version FROM ibex_core.sessions WHERE id = $1::uuid`, f.sessionID,
	).Scan(&v); err != nil {
		t.Fatalf("read fence version: %v", err)
	}
	return v
}

func TestRelayFenceChecker_DefinitionAndGrants(t *testing.T) {
	f := newRelayFenceFixture(t)

	var owner string
	var securityDefiner bool
	var volatility string
	err := f.db.QueryRowContext(f.ctx, `
		SELECT r.rolname, p.prosecdef, p.provolatile
		FROM pg_proc p
		JOIN pg_roles r ON r.oid = p.proowner
		WHERE p.oid = $1::regprocedure`,
		relayFenceFn+"(uuid,uuid,bigint)").Scan(&owner, &securityDefiner, &volatility)
	if err != nil {
		t.Fatalf("read function definition: %v", err)
	}
	if owner != "ibex_service" {
		t.Fatalf("owner: got %q want ibex_service", owner)
	}
	if !securityDefiner {
		t.Fatal("function must be SECURITY DEFINER")
	}
	if volatility != "s" {
		t.Fatalf("volatility: got %q want stable", volatility)
	}

	assertFenceExecutePrivilege(t, f, "ibex_evidence_relay", true)
	assertFenceExecutePrivilege(t, f, "ibex_app", false)
}

func assertFenceExecutePrivilege(t *testing.T, f *relayFenceFixture, role string, want bool) {
	t.Helper()
	var got bool
	if err := f.db.QueryRowContext(f.ctx,
		`SELECT has_function_privilege($1, $2, 'EXECUTE')`,
		role, relayFenceFn+"(uuid,uuid,bigint)",
	).Scan(&got); err != nil {
		t.Fatalf("has_function_privilege(%s): %v", role, err)
	}
	if got != want {
		t.Fatalf("execute privilege for %s: got %v want %v", role, got, want)
	}
}

func TestRelayFenceChecker_FenceOutcomes(t *testing.T) {
	f := newRelayFenceFixture(t)

	if got := f.checkFence(t, f.orgID, f.sessionID, 1); got != "alive" {
		t.Fatalf("live session: got %q want alive", got)
	}
	if got := f.checkFence(t, f.orgID, f.sessionID, 2); got != "stale_version" {
		t.Fatalf("version drift: got %q want stale_version", got)
	}
	if got := f.checkFence(t, f.orgID, uuid.NewString(), 1); got != "not_found" {
		t.Fatalf("unknown session: got %q want not_found", got)
	}
	if got := f.checkFence(t, f.otherOrg, f.sessionID, 1); got != "not_found" {
		t.Fatalf("cross-tenant session: got %q want not_found", got)
	}

	f.softDeleteSession(t)
	if v := f.sessionFenceVersion(t); v != 2 {
		t.Fatalf("fence version after soft delete: got %d want 2", v)
	}
	if got := f.checkFence(t, f.orgID, f.sessionID, 1); got != "tombstoned" {
		t.Fatalf("tombstoned pre-delete version: got %q want tombstoned", got)
	}
	if got := f.checkFence(t, f.orgID, f.sessionID, 2); got != "tombstoned" {
		t.Fatalf("tombstoned current version: got %q want tombstoned", got)
	}
}

// connAs opens a dedicated connection and switches it to a role via the given
// literal statement (e.g. "SET ROLE ibex_evidence_relay").
func (f *relayFenceFixture) connAs(t *testing.T, statement string) *sql.Conn {
	t.Helper()
	conn, err := f.db.Conn(f.ctx)
	if err != nil {
		t.Fatalf("conn: %v", err)
	}
	t.Cleanup(func() { _ = conn.Close() })
	if _, err := conn.ExecContext(f.ctx, statement); err != nil {
		t.Fatalf("role switch %q: %v", statement, err)
	}
	return conn
}

func TestRelayFenceChecker_RoleIsolation(t *testing.T) {
	f := newRelayFenceFixture(t)
	assertRelayRoleCanFenceButNotReadSessions(t, f)
	assertAppRoleCannotExecuteFence(t, f)
}

func assertRelayRoleCanFenceButNotReadSessions(t *testing.T, f *relayFenceFixture) {
	t.Helper()
	conn := f.connAs(t, "SET ROLE ibex_evidence_relay")

	var current string
	if err := conn.QueryRowContext(f.ctx, `SELECT current_user`).Scan(&current); err != nil {
		t.Fatalf("current_user: %v", err)
	}
	if current != "ibex_evidence_relay" {
		t.Fatalf("current_user: got %q want ibex_evidence_relay", current)
	}
	var outcome string
	if err := conn.QueryRowContext(f.ctx,
		`SELECT `+relayFenceFn+`($1::uuid, $2::uuid, $3)`, f.orgID, f.sessionID, 1,
	).Scan(&outcome); err != nil {
		t.Fatalf("relay role must execute fence check: %v", err)
	}
	if outcome != "alive" {
		t.Fatalf("relay role outcome: got %q want alive", outcome)
	}
	var count int
	err := conn.QueryRowContext(f.ctx, `SELECT COUNT(*) FROM ibex_core.sessions`).Scan(&count)
	if err == nil || !strings.Contains(err.Error(), "permission denied") {
		t.Fatalf("relay role must not read sessions directly, got count=%d err=%v", count, err)
	}
}

func assertAppRoleCannotExecuteFence(t *testing.T, f *relayFenceFixture) {
	t.Helper()
	conn := f.connAs(t, "SET ROLE ibex_app")
	var outcome string
	err := conn.QueryRowContext(f.ctx,
		`SELECT `+relayFenceFn+`($1::uuid, $2::uuid, $3)`, f.orgID, f.sessionID, 1,
	).Scan(&outcome)
	if err == nil || !strings.Contains(err.Error(), "permission denied") {
		t.Fatalf("ibex_app must not execute fence check, got outcome=%q err=%v", outcome, err)
	}
}

func TestRelayFenceChecker_DownRemovesFunction(t *testing.T) {
	f := newRelayFenceFixture(t)

	var exists bool
	if err := f.db.QueryRowContext(f.ctx,
		`SELECT to_regprocedure($1) IS NOT NULL`, relayFenceFn+"(uuid,uuid,bigint)",
	).Scan(&exists); err != nil {
		t.Fatalf("to_regprocedure: %v", err)
	}
	if !exists {
		t.Fatal("function must exist after up")
	}

	if err := Down(f.dsn); err != nil {
		t.Fatalf("down: %v", err)
	}
	if err := f.db.QueryRowContext(f.ctx,
		`SELECT to_regprocedure($1) IS NOT NULL`, relayFenceFn+"(uuid,uuid,bigint)",
	).Scan(&exists); err != nil {
		t.Fatalf("to_regprocedure after down: %v", err)
	}
	if exists {
		t.Fatal("function must be removed by down")
	}

	if err := Up(f.dsn); err != nil {
		t.Fatalf("re-up: %v", err)
	}
}
