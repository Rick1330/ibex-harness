//go:build integration

package postgres

import (
	"database/sql"
	"testing"
)

var sealedColumnCases = []struct {
	name    string
	allowed string
	denied  string
}{
	{"memory content", `SELECT org_id FROM ibex_core.memories LIMIT 0`, `SELECT content FROM ibex_core.memories LIMIT 1`},
	{"provider credentials", `SELECT org_id FROM ibex_core.provider_credentials LIMIT 0`, `SELECT ciphertext FROM ibex_core.provider_credentials LIMIT 1`},
	{"token hashes", `SELECT org_id FROM ibex_core.tokens LIMIT 0`, `SELECT hash FROM ibex_core.tokens LIMIT 1`},
	{"totp secrets", `SELECT org_id FROM ibex_core.user_totp_secrets LIMIT 0`, `SELECT ciphertext FROM ibex_core.user_totp_secrets LIMIT 1`},
}

// The purge role can read the org column its policies evaluate, but not content,
// credentials, hashes or secrets.
func TestTenancyPurgeCannotReadSecrets(t *testing.T) {
	f := newTenancyFixture(t)
	for _, tc := range sealedColumnCases {
		t.Run(tc.name, func(t *testing.T) { assertSealedColumn(f, tc.allowed, tc.denied) })
	}
}

func assertSealedColumn(f *tenancyFixture, allowed, denied string) {
	f.t.Helper()
	err := f.withRoleGUC("ibex_purge", "", func(tx *sql.Tx) error {
		if _, err := tx.ExecContext(f.ctx, allowed); err != nil {
			f.t.Fatalf("expected %q to be allowed: %v", allowed, err)
		}
		_, err := tx.ExecContext(f.ctx, denied)
		return err
	})
	f.requireSQLSTATE(err, "42501")
}

// The legal-hold trigger refuses an active hold only for ibex_purge; the owner
// and the explicit maintenance path remain able to delete.
func TestTenancyLegalHoldDeleteGuard(t *testing.T) {
	f := newTenancyFixture(t)
	f.seedTenant()
	f.seedLegalHold()
	assertOwnerCanDeleteHold(f)
	assertPurgeHoldGuard(f)
	assertServiceCannotDeleteHold(f)
	f.clearLegalHold()
	assertPurgeDeletesClearedHold(f)
}

func (f *tenancyFixture) seedLegalHold() {
	f.t.Helper()
	if _, err := f.db.ExecContext(f.ctx, `
		INSERT INTO ibex_core.legal_holds (org_id, reason, set_by)
		VALUES ($1::uuid, 'litigation', $2::uuid)`, f.orgID, f.userID); err != nil {
		f.t.Fatalf("seed hold: %v", err)
	}
}

func (f *tenancyFixture) clearLegalHold() {
	f.t.Helper()
	if _, err := f.db.ExecContext(f.ctx,
		`UPDATE ibex_core.legal_holds SET cleared_at = NOW() WHERE org_id = $1::uuid`, f.orgID); err != nil {
		f.t.Fatalf("clear hold: %v", err)
	}
}

func assertOwnerCanDeleteHold(f *tenancyFixture) {
	f.t.Helper()
	tx, err := f.db.BeginTx(f.ctx, nil)
	if err != nil {
		f.t.Fatalf("begin: %v", err)
	}
	defer func() { _ = tx.Rollback() }()
	if _, err := tx.ExecContext(f.ctx, `SET LOCAL ROLE ibex`); err != nil {
		f.t.Fatalf("set owner role: %v", err)
	}
	res, err := tx.ExecContext(f.ctx,
		`DELETE FROM ibex_core.legal_holds WHERE org_id = $1::uuid`, f.orgID)
	if err != nil {
		f.t.Fatalf("owner delete: %v", err)
	}
	if n, err := res.RowsAffected(); err != nil || n != 1 {
		f.t.Fatalf("owner delete affected %d rows (err=%v), want 1", n, err)
	}
}

func assertPurgeHoldGuard(f *tenancyFixture) {
	f.t.Helper()
	err := f.withRole("ibex_purge", f.orgID, func(tx *sql.Tx) error {
		res, err := tx.ExecContext(f.ctx,
			`DELETE FROM ibex_core.legal_holds WHERE org_id = $1::uuid AND cleared_at IS NOT NULL`, f.orgID)
		if err != nil {
			return err
		}
		if n, _ := res.RowsAffected(); n != 0 {
			f.t.Fatalf("saga-style delete removed %d active holds", n)
		}
		_, err = tx.ExecContext(f.ctx,
			`DELETE FROM ibex_core.legal_holds WHERE org_id = $1::uuid`, f.orgID)
		return err
	})
	f.requireSQLSTATE(err, "23514")
}

func assertServiceCannotDeleteHold(f *tenancyFixture) {
	f.t.Helper()
	err := f.withRole("ibex_service", f.orgID, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(f.ctx,
			`DELETE FROM ibex_core.legal_holds WHERE org_id = $1::uuid`, f.orgID)
		return err
	})
	f.requireSQLSTATE(err, "42501")
}

func assertPurgeDeletesClearedHold(f *tenancyFixture) {
	f.t.Helper()
	err := f.withRole("ibex_purge", f.orgID, func(tx *sql.Tx) error {
		res, err := tx.ExecContext(f.ctx,
			`DELETE FROM ibex_core.legal_holds WHERE org_id = $1::uuid AND cleared_at IS NOT NULL`, f.orgID)
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

// B5 — deleting a session fires clear_memory_session_id, which runs as
// ibex_purge; the memories UPDATE (session_id) grant makes the saga complete.
func TestTenancyPurgeDeletesSessionWithMemoryTrigger(t *testing.T) {
	f := newTenancyFixture(t)
	f.seedTenant()
	f.seedSessionAndMemory()

	err := f.withRole("ibex_purge", f.orgID, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(f.ctx,
			`DELETE FROM ibex_core.sessions WHERE org_id = $1::uuid`, f.orgID)
		return err
	})
	if err != nil {
		t.Fatalf("session delete as ibex_purge: %v", err)
	}
	var cleared bool
	if err := f.db.QueryRowContext(f.ctx,
		`SELECT session_id IS NULL FROM ibex_core.memories WHERE org_id = $1::uuid`, f.orgID).Scan(&cleared); err != nil {
		t.Fatalf("read memory: %v", err)
	}
	if !cleared {
		t.Fatal("clear_memory_session_id did not run as ibex_purge")
	}
}

func (f *tenancyFixture) seedSessionAndMemory() {
	f.t.Helper()
	var sessionID string
	if err := f.db.QueryRowContext(f.ctx, `
		INSERT INTO ibex_core.sessions (org_id, agent_id, model, provider, status)
		VALUES ($1::uuid, $2::uuid, 'm', 'p', 'active') RETURNING id::text`,
		f.orgID, f.agentID).Scan(&sessionID); err != nil {
		f.t.Fatalf("seed session: %v", err)
	}
	if _, err := f.db.ExecContext(f.ctx, `
		INSERT INTO ibex_core.memories (org_id, agent_id, session_id, content, content_hash, content_tokens)
		VALUES ($1::uuid, $2::uuid, $3::uuid, 'content', 'hash', 1)`,
		f.orgID, f.agentID, sessionID); err != nil {
		f.t.Fatalf("seed memory: %v", err)
	}
}
