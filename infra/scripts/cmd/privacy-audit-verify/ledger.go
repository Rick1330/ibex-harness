package main

import (
	"context"
	"database/sql"
	"fmt"

	"github.com/Rick1330/ibex-harness/packages/privacyaudit"
	"github.com/google/uuid"
)

// ResolveOrgs returns the -org filter when set, else distinct ledger org_ids via
// security-definer privacy_audit_list_orgs (works under FORCE RLS without forgeable GUCs).
func ResolveOrgs(ctx context.Context, db *sql.DB, orgFilter string) ([]uuid.UUID, error) {
	if orgFilter != "" {
		return privacyaudit.ResolveOrgs(ctx, nil, orgFilter)
	}
	conn, err := db.Conn(ctx)
	if err != nil {
		return nil, fmt.Errorf("privacy-audit-verify: conn: %w", err)
	}
	defer func() { _ = conn.Close() }()
	rows, err := conn.QueryContext(ctx, `SELECT org_id FROM ibex_core.privacy_audit_list_orgs()`)
	if err != nil {
		return nil, fmt.Errorf("privacy-audit-verify: list orgs: %w", err)
	}
	defer func() { _ = rows.Close() }()
	var out []uuid.UUID
	for rows.Next() {
		var id uuid.UUID
		if err := rows.Scan(&id); err != nil {
			return nil, err
		}
		out = append(out, id)
	}
	return out, rows.Err()
}

// VerifyOrg sets app.current_org_id inside a transaction (is_local=true), then verifies.
// Empty chains are OK when -org is explicitly set.
func VerifyOrg(ctx context.Context, db *sql.DB, org uuid.UUID) (int, error) {
	conn, err := db.Conn(ctx)
	if err != nil {
		return 0, fmt.Errorf("privacy-audit-verify: conn: %w", err)
	}
	defer func() { _ = conn.Close() }()
	tx, err := conn.BeginTx(ctx, nil)
	if err != nil {
		return 0, fmt.Errorf("privacy-audit-verify: begin: %w", err)
	}
	defer func() { _ = tx.Rollback() }()
	if err := privacyaudit.SetCurrentOrgID(ctx, tx, org); err != nil {
		return 0, err
	}
	n, verr := privacyaudit.VerifyOrg(ctx, tx, org)
	if verr != nil {
		return n, verr
	}
	if err := tx.Commit(); err != nil {
		return n, fmt.Errorf("privacy-audit-verify: commit: %w", err)
	}
	return n, nil
}
