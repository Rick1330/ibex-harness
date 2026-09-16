//go:build integration

package postgres

import (
	"context"
	"database/sql"
	"testing"
)

func TestPrivacyGovernance_LedgerAppendOnlyAndHold(t *testing.T) {
	dsn := testDSN()
	db := openTestDB(t)
	defer db.Close()
	resetSchema(t, db)
	if err := Up(dsn); err != nil {
		t.Fatalf("up: %v", err)
	}
	ctx := context.Background()
	orgID, userID := seedPrivacyOrg(t, ctx, db)
	assertLedgerChain(t, ctx, db, orgID, userID)
	assertLedgerAppendOnly(t, ctx, db, orgID)
	assertHoldAndCapturePolicy(t, ctx, db, orgID, userID)
	assertHoldBlockedJobStatus(t, ctx, db, orgID)
}

func seedPrivacyOrg(t *testing.T, ctx context.Context, db *sql.DB) (orgID, userID string) {
	t.Helper()
	err := withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		var e error
		orgID, e = insertOrg(ctx, tx, "Privacy Org", "privacy-org")
		if e != nil {
			return e
		}
		return insertUserAndAgent(ctx, tx, orgID, userAgentSeed{
			email: "privacy@example.com", name: "Privacy User", agent: "P Agent", slug: "p-agent",
		})
	})
	if err != nil {
		t.Fatalf("seed: %v", err)
	}
	err = withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		return tx.QueryRowContext(ctx, `
			SELECT id::text FROM ibex_core.users WHERE org_id = $1::uuid LIMIT 1`, orgID).Scan(&userID)
	})
	if err != nil {
		t.Fatalf("user id: %v", err)
	}
	return orgID, userID
}

func assertLedgerChain(t *testing.T, ctx context.Context, db *sql.DB, orgID, userID string) {
	t.Helper()
	var seq1, seq2 int64
	var prev2, hash1, hash2 string
	err := withOrgContext(ctx, db, orgID, func(tx *sql.Tx) error {
		var id, oid, prev string
		var created interface{}
		return tx.QueryRowContext(ctx, `
			SELECT id::text, org_id::text, seq, prev_hash, row_hash, created_at FROM ibex_core.privacy_audit_append(
				$1::uuid, $2::uuid, 'test.action', 'test', 'allow',
				'org', $1::text, ARRAY[]::TEXT[], NULL, NULL, NULL, NULL, NULL, '{}'::jsonb
			)`, orgID, userID).Scan(&id, &oid, &seq1, &prev, &hash1, &created)
	})
	if err != nil {
		t.Fatalf("append1: %v", err)
	}
	if seq1 != 1 {
		t.Fatalf("seq1=%d", seq1)
	}
	err = withOrgContext(ctx, db, orgID, func(tx *sql.Tx) error {
		var id, oid string
		var created interface{}
		return tx.QueryRowContext(ctx, `
			SELECT id::text, org_id::text, seq, prev_hash, row_hash, created_at FROM ibex_core.privacy_audit_append(
				$1::uuid, $2::uuid, 'test.action2', 'test', 'allow',
				'org', $1::text, ARRAY[]::TEXT[], NULL, NULL, NULL, NULL, NULL, '{"a":1}'::jsonb
			)`, orgID, userID).Scan(&id, &oid, &seq2, &prev2, &hash2, &created)
	})
	if err != nil {
		t.Fatalf("append2: %v", err)
	}
	if seq2 != 2 || prev2 != hash1 {
		t.Fatalf("seq2=%d prev2=%s hash1=%s hash2=%s", seq2, prev2, hash1, hash2)
	}
}

func assertLedgerAppendOnly(t *testing.T, ctx context.Context, db *sql.DB, orgID string) {
	t.Helper()
	err := withOrgContext(ctx, db, orgID, func(tx *sql.Tx) error {
		_, e := tx.ExecContext(ctx, `
			UPDATE ibex_core.privacy_audit_ledger SET action = 'forged' WHERE org_id = $1::uuid`, orgID)
		return e
	})
	if err == nil {
		t.Fatal("expected append-only update failure")
	}
}

func assertHoldAndCapturePolicy(t *testing.T, ctx context.Context, db *sql.DB, orgID, userID string) {
	t.Helper()
	err := withOrgContext(ctx, db, orgID, func(tx *sql.Tx) error {
		_, e := tx.ExecContext(ctx, `
			INSERT INTO ibex_core.legal_holds (org_id, scope, reason, set_by)
			VALUES ($1::uuid, 'org', 'litigation', $2::uuid)`, orgID, userID)
		return e
	})
	if err != nil {
		t.Fatalf("hold: %v", err)
	}
	err = withOrgContext(ctx, db, orgID, func(tx *sql.Tx) error {
		_, e := tx.ExecContext(ctx, `
			INSERT INTO ibex_core.org_capture_policies (org_id, mode, priority)
			VALUES ($1::uuid, 'metadata_only', 100)`, orgID)
		return e
	})
	if err != nil {
		t.Fatalf("capture policy: %v", err)
	}
}

func assertHoldBlockedJobStatus(t *testing.T, ctx context.Context, db *sql.DB, orgID string) {
	t.Helper()
	err := withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		_, e := tx.ExecContext(ctx, `
			INSERT INTO ibex_core.org_deletion_jobs (org_id, status)
			VALUES ($1::uuid, 'hold_blocked')`, orgID)
		return e
	})
	if err != nil {
		t.Fatalf("hold_blocked job: %v", err)
	}
}

// withOrgContext sets app.current_org_id (and service GUC) for privacy RLS + append auth.
func withOrgContext(ctx context.Context, db *sql.DB, orgID string, fn func(*sql.Tx) error) error {
	tx, err := db.BeginTx(ctx, nil)
	if err != nil {
		return err
	}
	defer func() { _ = tx.Rollback() }()
	if _, err := tx.ExecContext(ctx, `SELECT set_config('app.is_service_account', 'true', true)`); err != nil {
		return err
	}
	if _, err := tx.ExecContext(ctx, `SELECT set_config('app.current_org_id', $1, true)`, orgID); err != nil {
		return err
	}
	if err := fn(tx); err != nil {
		return err
	}
	return tx.Commit()
}
