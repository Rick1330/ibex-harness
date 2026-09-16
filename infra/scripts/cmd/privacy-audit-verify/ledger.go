package main

import (
	"context"
	"database/sql"
	"fmt"

	"github.com/Rick1330/ibex-harness/packages/privacyaudit"
	"github.com/google/uuid"
)

// ResolveOrgs returns the -org filter when set, else distinct ledger org_ids.
// Listing uses a dedicated connection so pool GUCs cannot leak across calls.
func ResolveOrgs(ctx context.Context, db *sql.DB, orgFilter string) ([]uuid.UUID, error) {
	if orgFilter != "" {
		return privacyaudit.ResolveOrgs(ctx, nil, orgFilter)
	}
	conn, err := db.Conn(ctx)
	if err != nil {
		return nil, fmt.Errorf("privacy-audit-verify: conn: %w", err)
	}
	defer conn.Close()
	return privacyaudit.ResolveOrgs(ctx, conn, "")
}

// VerifyOrg sets app.current_org_id on a dedicated connection, then verifies the chain.
// Empty chains are OK (including when -org is set). set_config failure is fatal.
func VerifyOrg(ctx context.Context, db *sql.DB, org uuid.UUID) (int, error) {
	conn, err := db.Conn(ctx)
	if err != nil {
		return 0, fmt.Errorf("privacy-audit-verify: conn: %w", err)
	}
	defer conn.Close()
	if err := privacyaudit.SetCurrentOrgID(ctx, conn, org); err != nil {
		return 0, err
	}
	return privacyaudit.VerifyOrg(ctx, conn, org)
}
