//go:build integration

package main

import (
	"context"
	"database/sql"
	"errors"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/infra/testing/testutil"
	"github.com/Rick1330/ibex-harness/packages/crypto"
	"github.com/Rick1330/ibex-harness/packages/permissions"
	"github.com/Rick1330/ibex-harness/services/auth/internal/token"
	"github.com/google/uuid"
)

const verifyTimeout = 10 * time.Second

func TestBootstrapIntegration(t *testing.T) {
	if os.Getenv("POSTGRES_TEST_DSN") == "" {
		t.Skip("POSTGRES_TEST_DSN not set")
	}
	f := newBootstrapFixture(t)

	first := f.run()
	assertFirstRun(t, first)
	f.verify(first, f.cfg.MemoryToken)

	second := f.run()
	assertAlreadyBootstrapped(t, second, true)

	oldToken := f.cfg.MemoryToken
	f.cfg.MemoryToken = generatePAT(t)
	third := f.run()
	assertAlreadyBootstrapped(t, third, true)
	f.verifyMemoryToken(first, f.cfg.MemoryToken)
	f.assertTokenInvalid(first, oldToken)

	f.revoke(first)
	_, err := bootstrap(context.Background(), f.db, f.cfg)
	assertRevokedRefusal(t, err)
	f.assertTokenRevoked(first)
}

type bootstrapFixture struct {
	t   *testing.T
	db  *sql.DB
	cfg bootstrapConfig
}

func newBootstrapFixture(t *testing.T) *bootstrapFixture {
	t.Helper()
	dsn, cleanup := testutil.SetupPostgres(t)
	t.Cleanup(cleanup)

	db, err := sql.Open("postgres", dsn)
	if err != nil {
		t.Fatalf("open db: %v", err)
	}
	t.Cleanup(func() { _ = db.Close() })

	cfg := bootstrapConfig{
		PostgresDSN: dsn,
		OrgName:     "Bootstrap Integration",
		OrgSlug:     "bootstrap-it-" + uuid.NewString(),
		UserEmail:   "owner@example.com",
		UserName:    "Owner",
		AgentName:   "Default Agent",
		AgentSlug:   "default",
		PATName:     "Bootstrap PAT",
		MemoryToken: generatePAT(t),
	}
	t.Cleanup(func() { cleanupBootstrapOrg(t, db, cfg.OrgSlug) })
	return &bootstrapFixture{t: t, db: db, cfg: cfg}
}

func (f *bootstrapFixture) run() bootstrapResult {
	f.t.Helper()
	result, err := bootstrap(context.Background(), f.db, f.cfg)
	if err != nil {
		f.t.Fatalf("bootstrap: %v", err)
	}
	return result
}

func (f *bootstrapFixture) verify(result bootstrapResult, memoryToken string) {
	f.t.Helper()
	ctx, tx := f.begin()
	v := bootstrapVerifier{t: f.t, ctx: ctx, tx: tx, result: result}
	v.organization()
	v.ownerAndAgent()
	v.modelPolicy()
	v.pat()
	v.memoryToken(memoryToken)
}

func (f *bootstrapFixture) verifyMemoryToken(result bootstrapResult, bearer string) {
	f.t.Helper()
	ctx, tx := f.begin()
	v := bootstrapVerifier{t: f.t, ctx: ctx, tx: tx, result: result}
	v.memoryToken(bearer)
}

func (f *bootstrapFixture) begin() (context.Context, *sql.Tx) {
	f.t.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), verifyTimeout)
	f.t.Cleanup(cancel)
	tx, err := f.db.BeginTx(ctx, nil)
	if err != nil {
		f.t.Fatalf("begin verification transaction: %v", err)
	}
	f.t.Cleanup(func() { _ = tx.Rollback() })
	if _, err := tx.ExecContext(ctx, `SELECT set_config('app.is_service_account', 'true', true)`); err != nil {
		f.t.Fatalf("set service-account session: %v", err)
	}
	return ctx, tx
}

func (f *bootstrapFixture) revoke(result bootstrapResult) {
	f.t.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), verifyTimeout)
	defer cancel()
	if _, err := f.db.ExecContext(ctx, `
		UPDATE ibex_core.tokens
		SET is_revoked = true, revoked_at = NOW(), revoke_reason = 'integration test'
		WHERE agent_id = $1 AND type = 'service_token'`, result.AgentID.String()); err != nil {
		f.t.Fatalf("revoke memory service token: %v", err)
	}
}

func (f *bootstrapFixture) assertTokenInvalid(result bootstrapResult, bearer string) {
	f.t.Helper()
	var hash string
	if err := f.db.QueryRowContext(context.Background(), `
		SELECT hash FROM ibex_core.tokens
		WHERE agent_id = $1 AND type = 'service_token'`,
		result.AgentID.String(),
	).Scan(&hash); err != nil {
		f.t.Fatalf("read rotated memory token hash: %v", err)
	}
	ok, err := crypto.VerifyToken(bearer, hash, crypto.ProductionParams())
	if err != nil {
		f.t.Fatalf("verify rotated-away memory token: %v", err)
	}
	if ok {
		f.t.Fatal("rotated-away memory token still verifies against the stored hash")
	}
}

func (f *bootstrapFixture) assertTokenRevoked(result bootstrapResult) {
	f.t.Helper()
	var revoked bool
	if err := f.db.QueryRowContext(context.Background(), `
		SELECT is_revoked FROM ibex_core.tokens
		WHERE agent_id = $1 AND type = 'service_token'`,
		result.AgentID.String(),
	).Scan(&revoked); err != nil {
		f.t.Fatalf("read revoked memory service token: %v", err)
	}
	if !revoked {
		f.t.Fatal("bootstrap reactivated a revoked memory service token")
	}
}

type bootstrapVerifier struct {
	t      *testing.T
	ctx    context.Context
	tx     *sql.Tx
	result bootstrapResult
}

func (v bootstrapVerifier) organization() {
	v.t.Helper()
	var profile, model string
	var dim int
	mustScan(v.t, v.tx.QueryRowContext(v.ctx, `
		SELECT embedding_profile, embedding_dim, embedding_model_id
		FROM ibex_core.organizations WHERE id = $1`, v.result.OrgID.String()),
		&profile, &dim, &model)
	if profile != "gpu" {
		v.t.Fatalf("organization embedding profile = %q", profile)
	}
	if dim != 1024 {
		v.t.Fatalf("organization embedding dim = %d", dim)
	}
	if model != "BAAI/bge-m3" {
		v.t.Fatalf("organization embedding model = %q", model)
	}
}

func (v bootstrapVerifier) ownerAndAgent() {
	v.t.Helper()
	var role, userStatus string
	mustScan(v.t, v.tx.QueryRowContext(v.ctx,
		`SELECT role, status FROM ibex_core.users WHERE id = $1`, v.result.UserID.String()),
		&role, &userStatus)
	if role != "owner" || userStatus != "active" {
		v.t.Fatalf("owner user = %s/%s", role, userStatus)
	}

	var agentStatus string
	var createdBy uuid.UUID
	mustScan(v.t, v.tx.QueryRowContext(v.ctx,
		`SELECT status, created_by FROM ibex_core.agents WHERE id = $1`, v.result.AgentID.String()),
		&agentStatus, &createdBy)
	if agentStatus != "active" || createdBy != v.result.UserID {
		v.t.Fatalf("agent status/created_by = %s/%s", agentStatus, createdBy)
	}
}

func (v bootstrapVerifier) modelPolicy() {
	v.t.Helper()
	var pattern string
	var allowed bool
	var priority int
	mustScan(v.t, v.tx.QueryRowContext(v.ctx, `
		SELECT model_pattern, allowed, priority
		FROM ibex_core.org_model_policies WHERE org_id = $1`, v.result.OrgID.String()),
		&pattern, &allowed, &priority)
	if pattern != "*" {
		v.t.Fatalf("model policy pattern = %q", pattern)
	}
	if !allowed {
		v.t.Fatal("model policy must allow the model")
	}
	if priority != 1000 {
		v.t.Fatalf("model policy priority = %d", priority)
	}

	var epoch int64
	mustScan(v.t, v.tx.QueryRowContext(v.ctx,
		`SELECT epoch FROM ibex_core.org_model_policy_meta WHERE org_id = $1`, v.result.OrgID.String()),
		&epoch)
	if epoch != 1 {
		v.t.Fatalf("model policy epoch = %d", epoch)
	}
}

type tokenRow struct {
	tokenType string
	hash      string
	userID    uuid.UUID
	agentID   uuid.UUID
	perms     int64
	revoked   bool
	expires   sql.NullTime
}

func (v bootstrapVerifier) pat() {
	v.t.Helper()
	var row tokenRow
	mustScan(v.t, v.tx.QueryRowContext(v.ctx, `
		SELECT type, hash, user_id, agent_id, permissions, is_revoked, expires_at
		FROM ibex_core.tokens WHERE agent_id = $1 AND type = 'pat'`, v.result.AgentID.String()),
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
	ok, err := crypto.VerifyToken(result.PAT, row.hash, crypto.ProductionParams())
	if err != nil {
		t.Fatalf("verify bootstrap PAT hash: %v", err)
	}
	if !ok {
		t.Fatal("stored hash does not verify the printed PAT")
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

func (v bootstrapVerifier) memoryToken(bearer string) {
	v.t.Helper()
	var row serviceTokenDBRow
	mustScan(v.t, v.tx.QueryRowContext(v.ctx, `
		SELECT hash, prefix, name, user_id, agent_id, permissions
		FROM ibex_core.tokens WHERE agent_id = $1 AND type = 'service_token'`,
		v.result.AgentID.String()),
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
	ok, err := crypto.VerifyToken(bearer, row.hash, crypto.ProductionParams())
	if err != nil {
		t.Fatalf("verify memory token hash: %v", err)
	}
	if !ok {
		t.Fatal("stored hash does not verify the memory service token")
	}
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

func assertFirstRun(t *testing.T, result bootstrapResult) {
	t.Helper()
	if result.AlreadyBootstrapped {
		t.Fatal("first bootstrap reported already bootstrapped")
	}
	if result.PAT == "" {
		t.Fatal("first bootstrap returned an empty PAT")
	}
}

func assertAlreadyBootstrapped(t *testing.T, result bootstrapResult, memoryManaged bool) {
	t.Helper()
	if !result.AlreadyBootstrapped {
		t.Fatal("bootstrap created a second organization")
	}
	if result.PAT != "" {
		t.Fatal("bootstrap rotated or returned a PAT")
	}
	if result.MemoryTokenManaged != memoryManaged {
		t.Fatalf("memory token managed = %t, want %t", result.MemoryTokenManaged, memoryManaged)
	}
}

func assertRevokedRefusal(t *testing.T, err error) {
	t.Helper()
	if err == nil || !strings.Contains(err.Error(), "revoked") {
		t.Fatalf("bootstrap after revocation error = %v, want a revoked-token refusal", err)
	}
}

func cleanupBootstrapOrg(t *testing.T, db *sql.DB, slug string) {
	t.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), verifyTimeout)
	defer cancel()

	tx, err := db.BeginTx(ctx, nil)
	if err != nil {
		t.Logf("cleanup: begin: %v", err)
		return
	}
	defer func() { _ = tx.Rollback() }()
	if _, err := tx.ExecContext(ctx, `SELECT set_config('app.is_service_account', 'true', true)`); err != nil {
		t.Logf("cleanup: set service-account session: %v", err)
		return
	}

	var orgID uuid.UUID
	err = tx.QueryRowContext(ctx,
		`SELECT id FROM ibex_core.organizations WHERE slug = $1`, slug,
	).Scan(&orgID)
	if errors.Is(err, sql.ErrNoRows) {
		return
	}
	if err != nil {
		t.Logf("cleanup: lookup organization: %v", err)
		return
	}

	for _, query := range []string{
		`DELETE FROM ibex_core.tokens WHERE org_id = $1`,
		`DELETE FROM ibex_core.agents WHERE org_id = $1`,
		`DELETE FROM ibex_core.users WHERE org_id = $1`,
		`DELETE FROM ibex_core.org_model_policies WHERE org_id = $1`,
		`DELETE FROM ibex_core.org_model_policy_meta WHERE org_id = $1`,
		`DELETE FROM ibex_core.organizations WHERE id = $1`,
	} {
		if _, err := tx.ExecContext(ctx, query, orgID.String()); err != nil {
			t.Logf("cleanup: %s: %v", query, err)
			return
		}
	}
	if err := tx.Commit(); err != nil {
		t.Logf("cleanup: commit: %v", err)
	}
}
