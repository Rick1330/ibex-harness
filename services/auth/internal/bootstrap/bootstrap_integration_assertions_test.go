//go:build integration

package bootstrap

import (
	"context"
	"database/sql"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/crypto"
	"github.com/Rick1330/ibex-harness/packages/permissions"
	"github.com/Rick1330/ibex-harness/services/auth/internal/token"
	"github.com/google/uuid"
)

type tokenRow struct {
	tokenType string
	hash      string
	userID    uuid.UUID
	agentID   uuid.UUID
	perms     int64
	revoked   bool
	expires   sql.NullTime
}

func (v bootstrapVerifier) pat(ctx context.Context) {
	v.t.Helper()
	var row tokenRow
	mustScan(v.t, v.tx.QueryRowContext(ctx, `
		SELECT type, hash, user_id, agent_id, permissions, is_revoked, expires_at
		FROM ibex_core.tokens WHERE agent_id = $1 AND org_id = $2 AND type = 'pat'`,
		v.result.AgentID.String(), v.result.OrgID.String()),
		&row.tokenType, &row.hash, &row.userID, &row.agentID, &row.perms, &row.revoked, &row.expires)
	assertPAT(v.t, row, v.result)
}

func assertPAT(t *testing.T, row tokenRow, result bootstrapResult) {
	t.Helper()
	assertPATSubject(t, row, result)
	assertPATActive(t, row)
	assertPATPermissions(t, row)
	assertPATHash(t, row, result)
}

func assertPATSubject(t *testing.T, row tokenRow, result bootstrapResult) {
	t.Helper()
	if row.tokenType != "pat" {
		t.Fatalf("token type = %q", row.tokenType)
	}
	if row.userID != result.UserID {
		t.Fatalf("token user = %s", row.userID)
	}
	if row.agentID != result.AgentID {
		t.Fatalf("token agent = %s", row.agentID)
	}
}

func assertPATActive(t *testing.T, row tokenRow) {
	t.Helper()
	if row.revoked {
		t.Fatal("token must not be revoked")
	}
	if row.expires.Valid {
		t.Fatalf("token must not expire: %v", row.expires)
	}
}

func assertPATPermissions(t *testing.T, row tokenRow) {
	t.Helper()
	if row.perms != bootstrapPermissions() {
		t.Fatalf("token permissions = %d, want %d", row.perms, bootstrapPermissions())
	}
	if !permissions.Has(row.perms, permissions.Admin|permissions.SecretUse|permissions.OperatorMetadataRead) {
		t.Fatalf("token permissions %d miss a required bit", row.perms)
	}
}

func assertPATHash(t *testing.T, row tokenRow, result bootstrapResult) {
	t.Helper()
	assertHashValid(t, result.PAT, row.hash, "the bootstrap PAT")
}

func assertHashValid(t *testing.T, bearer, hash, label string) {
	t.Helper()
	ok, err := crypto.VerifyToken(bearer, hash, crypto.ProductionParams())
	if err != nil {
		t.Fatalf("verify %s hash: %v", label, err)
	}
	if !ok {
		t.Fatalf("stored hash does not verify %s", label)
	}
}

type serviceTokenDBRow struct {
	hash    string
	prefix  string
	name    string
	userID  uuid.UUID
	agentID uuid.UUID
	perms   int64
}

func (v bootstrapVerifier) memoryToken(ctx context.Context, bearer string) {
	v.t.Helper()
	var row serviceTokenDBRow
	mustScan(v.t, v.tx.QueryRowContext(ctx, `
		SELECT hash, prefix, name, user_id, agent_id, permissions
		FROM ibex_core.tokens WHERE agent_id = $1 AND org_id = $2 AND type = 'service_token'`,
		v.result.AgentID.String(), v.result.OrgID.String()),
		&row.hash, &row.prefix, &row.name, &row.userID, &row.agentID, &row.perms)
	assertServiceToken(v.t, row, v.result, bearer)
}

func assertServiceToken(t *testing.T, row serviceTokenDBRow, result bootstrapResult, bearer string) {
	t.Helper()
	assertServiceTokenSubject(t, row, result)
	assertServiceTokenPrefix(t, row, bearer)
	assertServiceTokenPermissions(t, row)
	assertServiceTokenHash(t, row, bearer)
}

func assertServiceTokenSubject(t *testing.T, row serviceTokenDBRow, result bootstrapResult) {
	t.Helper()
	if row.userID != result.UserID {
		t.Fatalf("memory token user = %s", row.userID)
	}
	if row.agentID != result.AgentID {
		t.Fatalf("memory token agent = %s", row.agentID)
	}
	if row.name != "memory-service" {
		t.Fatalf("memory token name = %q", row.name)
	}
}

func assertServiceTokenPrefix(t *testing.T, row serviceTokenDBRow, bearer string) {
	t.Helper()
	parsed, err := token.ParsePAT(bearer)
	if err != nil {
		t.Fatalf("parse memory token: %v", err)
	}
	if row.prefix != parsed.Prefix {
		t.Fatalf("memory token prefix = %q, want %q", row.prefix, parsed.Prefix)
	}
}

func assertServiceTokenPermissions(t *testing.T, row serviceTokenDBRow) {
	t.Helper()
	wantPerms := permissions.MemoryRead | permissions.MemoryWrite
	if row.perms != wantPerms {
		t.Fatalf("memory token permissions = %d, want %d", row.perms, wantPerms)
	}
}

func assertServiceTokenHash(t *testing.T, row serviceTokenDBRow, bearer string) {
	t.Helper()
	assertHashValid(t, bearer, row.hash, "the memory service token")
}

func mustScan(t *testing.T, row *sql.Row, dest ...any) {
	t.Helper()
	if err := row.Scan(dest...); err != nil {
		t.Fatalf("scan row: %v", err)
	}
}

func generatePAT(t *testing.T) string {
	t.Helper()
	pat, _, _, err := token.GeneratePAT()
	if err != nil {
		t.Fatalf("generate PAT: %v", err)
	}
	return pat
}
