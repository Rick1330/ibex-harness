//go:build integration

package postgres

import (
	"context"
	"database/sql"
	"testing"
)

// sealedColumnCase is one allowed/denied column pair for the purge role.
type sealedColumnCase struct {
	name    string
	allowed string
	denied  string
}

// sealedColumnCases covers content, credentials, hashes and TOTP secrets.
var sealedColumnCases = []sealedColumnCase{
	{"memory content", `SELECT org_id FROM ibex_core.memories LIMIT 0`, `SELECT content FROM ibex_core.memories LIMIT 1`},
	{"provider credentials", `SELECT org_id FROM ibex_core.provider_credentials LIMIT 0`, `SELECT ciphertext FROM ibex_core.provider_credentials LIMIT 1`},
	{"token hashes", `SELECT org_id FROM ibex_core.tokens LIMIT 0`, `SELECT hash FROM ibex_core.tokens LIMIT 1`},
	{"totp secrets", `SELECT org_id FROM ibex_core.user_totp_secrets LIMIT 0`, `SELECT ciphertext FROM ibex_core.user_totp_secrets LIMIT 1`},
}

// purgeCounts is the row counts observed during the scoped purge proof.
type purgeCounts struct {
	sessionsA, sessionsB int64
	holdsA, holdsB       int64
}

// TestTenancyPurgeCannotReadSecrets proves the purge role cannot read content.
func TestTenancyPurgeCannotReadSecrets(t *testing.T) {
	f := newTenancyFixture(t)
	ctx := t.Context()
	for _, tc := range sealedColumnCases {
		t.Run(tc.name, func(t *testing.T) { assertSealedColumn(f, ctx, tc) })
	}
}

// assertSealedColumn checks one allowed column and one denied column.
func assertSealedColumn(f *tenancyFixture, ctx context.Context, tc sealedColumnCase) {
	f.t.Helper()
	err := f.withRole(ctx, role("ibex_purge").withGUC(""), func(tx *sql.Tx) error {
		if _, err := tx.ExecContext(ctx, tc.allowed); err != nil {
			f.t.Fatalf("expected %q to be allowed: %v", tc.allowed, err)
		}
		_, err := tx.ExecContext(ctx, tc.denied)
		return err
	})
	f.requireSQLSTATE(err, sqlState{code: "42501"})
}

// TestTenancyLegalHoldDeleteGuard proves the trigger constrains only ibex_purge.
func TestTenancyLegalHoldDeleteGuard(t *testing.T) {
	f := newTenancyFixture(t)
	ctx := t.Context()
	f.seedTenant(ctx)
	seed := tenantSeed{orgID: f.orgID, userID: f.userID, agentID: f.agentID}
	f.seedLegalHold(ctx, seed)
	assertOwnerCanDeleteHold(f, ctx, seed)
	assertPurgeHoldGuard(f, ctx, seed)
	assertServiceCannotDeleteHold(f, ctx, seed)
	f.clearLegalHold(ctx, seed)
	assertPurgeDeletesClearedHold(f, ctx, seed)
}

// seedLegalHold inserts one active hold.
func (f *tenancyFixture) seedLegalHold(ctx context.Context, seed tenantSeed) {
	f.t.Helper()
	if _, err := f.db.ExecContext(ctx, `
		INSERT INTO ibex_core.legal_holds (org_id, reason, set_by)
		VALUES ($1::uuid, 'litigation', $2::uuid)`, seed.orgID, seed.userID); err != nil {
		f.t.Fatalf("seed hold: %v", err)
	}
}

// clearLegalHold marks the tenant's hold cleared.
func (f *tenancyFixture) clearLegalHold(ctx context.Context, seed tenantSeed) {
	f.t.Helper()
	if _, err := f.db.ExecContext(ctx,
		`UPDATE ibex_core.legal_holds SET cleared_at = NOW() WHERE org_id = $1::uuid`, seed.orgID); err != nil {
		f.t.Fatalf("clear hold: %v", err)
	}
}

// assertOwnerCanDeleteHold proves the owner path is not blocked.
func assertOwnerCanDeleteHold(f *tenancyFixture, ctx context.Context, seed tenantSeed) {
	f.t.Helper()
	tx, err := f.db.BeginTx(ctx, nil)
	if err != nil {
		f.t.Fatalf("begin: %v", err)
	}
	defer func() { _ = tx.Rollback() }()
	if _, err := tx.ExecContext(ctx, `SET LOCAL ROLE ibex`); err != nil {
		f.t.Fatalf("set owner role: %v", err)
	}
	res, err := tx.ExecContext(ctx,
		`DELETE FROM ibex_core.legal_holds WHERE org_id = $1::uuid`, seed.orgID)
	if err != nil {
		f.t.Fatalf("owner delete: %v", err)
	}
	if n, _ := res.RowsAffected(); n != 1 {
		f.t.Fatalf("owner delete affected %d rows, want 1", n)
	}
}

// assertPurgeHoldGuard proves ibex_purge cannot delete an active hold.
func assertPurgeHoldGuard(f *tenancyFixture, ctx context.Context, seed tenantSeed) {
	f.t.Helper()
	err := f.withRole(ctx, role("ibex_purge").withGUC(seed.orgID), func(tx *sql.Tx) error {
		res, err := tx.ExecContext(ctx,
			`DELETE FROM ibex_core.legal_holds WHERE org_id = $1::uuid AND cleared_at IS NOT NULL`, seed.orgID)
		if err != nil {
			return err
		}
		if n, _ := res.RowsAffected(); n != 0 {
			f.t.Fatalf("saga-style delete removed %d active holds", n)
		}
		_, err = tx.ExecContext(ctx,
			`DELETE FROM ibex_core.legal_holds WHERE org_id = $1::uuid`, seed.orgID)
		return err
	})
	f.requireSQLSTATE(err, sqlState{code: "23514"})
}

// assertServiceCannotDeleteHold proves ibex_service lost the DELETE verb.
func assertServiceCannotDeleteHold(f *tenancyFixture, ctx context.Context, seed tenantSeed) {
	f.t.Helper()
	err := f.withRole(ctx, role("ibex_service").withGUC(seed.orgID), func(tx *sql.Tx) error {
		_, err := tx.ExecContext(ctx,
			`DELETE FROM ibex_core.legal_holds WHERE org_id = $1::uuid`, seed.orgID)
		return err
	})
	f.requireSQLSTATE(err, sqlState{code: "42501"})
}

// assertPurgeDeletesClearedHold proves the purge can remove a cleared hold.
func assertPurgeDeletesClearedHold(f *tenancyFixture, ctx context.Context, seed tenantSeed) {
	f.t.Helper()
	err := f.withRole(ctx, role("ibex_purge").withGUC(seed.orgID), func(tx *sql.Tx) error {
		res, err := tx.ExecContext(ctx,
			`DELETE FROM ibex_core.legal_holds WHERE org_id = $1::uuid AND cleared_at IS NOT NULL`, seed.orgID)
		if err != nil {
			return err
		}
		if n, _ := res.RowsAffected(); n != 1 {
			f.t.Fatalf("cleared hold delete affected %d rows, want 1", n)
		}
		return nil
	})
	if err != nil {
		f.t.Fatalf("cleared hold delete: %v", err)
	}
}

// purgeTenants is the primary and other tenant for the scoped purge proof.
type purgeTenants struct {
	a, b tenantSeed
}

// TestTenancyPurgeDeletesSessionWithMemoryTrigger proves the session trigger
// completes and that the org GUC scopes the purge to one tenant.
func TestTenancyPurgeDeletesSessionWithMemoryTrigger(t *testing.T) {
	f := newTenancyFixture(t)
	ctx := t.Context()
	f.seedTenant(ctx)
	other := f.seedTenantNamed(ctx, "other-org")
	primary := tenantSeed{orgID: f.orgID, userID: f.userID, agentID: f.agentID}
	f.seedSessionAndMemory(ctx, primary)
	f.seedSessionAndMemory(ctx, other)
	f.seedClearedHold(ctx, primary)
	f.seedClearedHold(ctx, other)
	assertPurgeScopedToOneOrg(t, f, ctx, purgeTenants{a: primary, b: other})
}

// seedSessionAndMemory inserts one session and one memory linked to it.
func (f *tenancyFixture) seedSessionAndMemory(ctx context.Context, seed tenantSeed) {
	f.t.Helper()
	var sessionID string
	if err := f.db.QueryRowContext(ctx, `
		INSERT INTO ibex_core.sessions (org_id, agent_id, model, provider, status)
		VALUES ($1::uuid, $2::uuid, 'm', 'p', 'active') RETURNING id::text`,
		seed.orgID, seed.agentID).Scan(&sessionID); err != nil {
		f.t.Fatalf("seed session: %v", err)
	}
	if _, err := f.db.ExecContext(ctx, `
		INSERT INTO ibex_core.memories (org_id, agent_id, session_id, content, content_hash, content_tokens)
		VALUES ($1::uuid, $2::uuid, $3::uuid, 'content', 'hash', 1)`,
		seed.orgID, seed.agentID, sessionID); err != nil {
		f.t.Fatalf("seed memory: %v", err)
	}
}

// seedClearedHold inserts one already-cleared hold.
func (f *tenancyFixture) seedClearedHold(ctx context.Context, seed tenantSeed) {
	f.t.Helper()
	if _, err := f.db.ExecContext(ctx, `
		INSERT INTO ibex_core.legal_holds (org_id, reason, set_by, cleared_at)
		VALUES ($1::uuid, 'cleared', $2::uuid, NOW())`, seed.orgID, seed.userID); err != nil {
		f.t.Fatalf("seed cleared hold: %v", err)
	}
}

// assertPurgeScopedToOneOrg deletes as ibex_purge scoped to A and checks B.
func assertPurgeScopedToOneOrg(t *testing.T, f *tenancyFixture, ctx context.Context, tenants purgeTenants) {
	t.Helper()
	counts, err := f.runScopedPurge(ctx, tenants.a.orgID, tenants.b.orgID)
	if err != nil {
		t.Fatalf("scoped purge: %v", err)
	}
	assertPurgeCounts(t, counts)
	assertOtherTenantIntact(t, f, ctx, tenants.b)
}

// runScopedPurge runs the four deletes under one org-A GUC.
func (f *tenancyFixture) runScopedPurge(ctx context.Context, orgA, orgB string) (purgeCounts, error) {
	counts := purgeCounts{}
	err := f.withRole(ctx, role("ibex_purge").withGUC(orgA), func(tx *sql.Tx) error {
		var err error
		counts.sessionsA, err = deleteOrgRows(ctx, tx, `DELETE FROM ibex_core.sessions WHERE org_id = $1::uuid`, orgA)
		if err != nil {
			return err
		}
		counts.sessionsB, err = deleteOrgRows(ctx, tx, `DELETE FROM ibex_core.sessions WHERE org_id = $1::uuid`, orgB)
		if err != nil {
			return err
		}
		counts.holdsA, err = deleteOrgRows(ctx, tx, `DELETE FROM ibex_core.legal_holds WHERE org_id = $1::uuid AND cleared_at IS NOT NULL`, orgA)
		if err != nil {
			return err
		}
		counts.holdsB, err = deleteOrgRows(ctx, tx, `DELETE FROM ibex_core.legal_holds WHERE org_id = $1::uuid AND cleared_at IS NOT NULL`, orgB)
		return err
	})
	return counts, err
}

// assertPurgeCounts checks the primary and other-tenant row counts.
func assertPurgeCounts(t *testing.T, counts purgeCounts) {
	t.Helper()
	if counts.sessionsA != 1 {
		t.Fatalf("primary sessions deleted = %d, want 1", counts.sessionsA)
	}
	if counts.holdsA != 1 {
		t.Fatalf("primary holds deleted = %d, want 1", counts.holdsA)
	}
	if counts.sessionsB != 0 {
		t.Fatalf("other-tenant sessions deleted = %d, want 0", counts.sessionsB)
	}
	if counts.holdsB != 0 {
		t.Fatalf("other-tenant holds deleted = %d, want 0", counts.holdsB)
	}
}

// deleteOrgRows executes a DELETE and returns its affected row count.
func deleteOrgRows(ctx context.Context, tx *sql.Tx, query, orgID string) (int64, error) {
	res, err := tx.ExecContext(ctx, query, orgID)
	if err != nil {
		return 0, err
	}
	return res.RowsAffected()
}

// assertOtherTenantIntact proves B's session, hold and memory link survived.
func assertOtherTenantIntact(t *testing.T, f *tenancyFixture, ctx context.Context, other tenantSeed) {
	t.Helper()
	var sessions, holds int
	if err := f.db.QueryRowContext(ctx, `
		SELECT COUNT(*) FROM ibex_core.sessions WHERE org_id = $1::uuid`, other.orgID).Scan(&sessions); err != nil {
		t.Fatalf("count other sessions: %v", err)
	}
	if sessions != 1 {
		t.Fatalf("other tenant sessions = %d, want 1", sessions)
	}
	if err := f.db.QueryRowContext(ctx, `
		SELECT COUNT(*) FROM ibex_core.legal_holds WHERE org_id = $1::uuid`, other.orgID).Scan(&holds); err != nil {
		t.Fatalf("count other holds: %v", err)
	}
	if holds != 1 {
		t.Fatalf("other tenant holds = %d, want 1", holds)
	}
	var linked bool
	if err := f.db.QueryRowContext(ctx, `
		SELECT session_id IS NOT NULL FROM ibex_core.memories WHERE org_id = $1::uuid`, other.orgID).Scan(&linked); err != nil {
		t.Fatalf("read other memory: %v", err)
	}
	if !linked {
		t.Fatal("other tenant memory lost its session link")
	}
}
