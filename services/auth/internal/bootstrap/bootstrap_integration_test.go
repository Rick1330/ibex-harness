//go:build integration

package bootstrap

import (
	"bytes"
	"context"
	"database/sql"
	"errors"
	"os"
	"path/filepath"
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
	f.verifyPAT(first)
	f.verifyCrossTenant()

	oldToken := f.cfg.MemoryToken
	f.cfg.MemoryToken = generatePAT(t)
	third := f.run()
	assertAlreadyBootstrapped(t, third, true)
	f.verifyPAT(first)
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
	v := bootstrapVerifier{t: f.t, tx: tx, result: result}
	v.organization(ctx)
	v.ownerAndAgent(ctx)
	v.modelPolicy(ctx)
	v.pat(ctx)
	v.memoryToken(ctx, memoryToken)
}

func (f *bootstrapFixture) verifyMemoryToken(result bootstrapResult, bearer string) {
	f.t.Helper()
	ctx, tx := f.begin()
	v := bootstrapVerifier{t: f.t, tx: tx, result: result}
	v.memoryToken(ctx, bearer)
}

func (f *bootstrapFixture) verifyPAT(result bootstrapResult) {
	f.t.Helper()
	ctx, tx := f.begin()
	v := bootstrapVerifier{t: f.t, tx: tx, result: result}
	v.pat(ctx)
}

// verifyCrossTenant creates a second organization, rotates the first
// organization's memory token, and proves the second organization's identity
// and token are untouched.
func (f *bootstrapFixture) verifyCrossTenant() {
	f.t.Helper()
	other := f.cfg
	other.OrgSlug = "bootstrap-it-other-" + uuid.NewString()
	other.UserEmail = "other-owner@example.com"
	other.MemoryToken = generatePAT(f.t)
	f.t.Cleanup(func() { cleanupBootstrapOrg(f.t, f.db, other.OrgSlug) })

	otherResult, err := bootstrap(context.Background(), f.db, other)
	if err != nil {
		f.t.Fatalf("bootstrap other organization: %v", err)
	}
	if otherResult.AlreadyBootstrapped {
		f.t.Fatal("other organization already bootstrapped")
	}

	f.cfg.MemoryToken = generatePAT(f.t)
	f.run()

	f.verifyMemoryToken(otherResult, other.MemoryToken)
}

func (f *bootstrapFixture) begin() (context.Context, *sql.Tx) {
	return openServiceTx(f.t, f.db)
}

func openServiceTx(t *testing.T, db *sql.DB) (context.Context, *sql.Tx) {
	t.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), verifyTimeout)
	t.Cleanup(cancel)
	tx, err := db.BeginTx(ctx, nil)
	if err != nil {
		t.Fatalf("begin service transaction: %v", err)
	}
	t.Cleanup(func() { _ = tx.Rollback() })
	if _, err := tx.ExecContext(ctx, `SELECT set_config('app.is_service_account', 'true', true)`); err != nil {
		t.Fatalf("set service-account session: %v", err)
	}
	return ctx, tx
}

func (f *bootstrapFixture) execServiceTx(fn func(context.Context, *sql.Tx)) {
	ctx, tx := openServiceTx(f.t, f.db)
	fn(ctx, tx)
	if err := tx.Commit(); err != nil {
		f.t.Fatalf("commit service transaction: %v", err)
	}
}

func (f *bootstrapFixture) revoke(result bootstrapResult) {
	f.t.Helper()
	f.execServiceTx(func(ctx context.Context, tx *sql.Tx) {
		if _, err := tx.ExecContext(ctx, `
			UPDATE ibex_core.tokens
			SET is_revoked = true, revoked_at = NOW(), revoke_reason = 'integration test'
			WHERE agent_id = $1 AND type = 'service_token'`, result.AgentID.String()); err != nil {
			f.t.Fatalf("revoke memory service token: %v", err)
		}
	})
}

func (f *bootstrapFixture) assertTokenInvalid(result bootstrapResult, bearer string) {
	f.t.Helper()
	ctx, tx := f.begin()
	var hash string
	if err := tx.QueryRowContext(ctx, `
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
	ctx, tx := f.begin()
	var revoked bool
	if err := tx.QueryRowContext(ctx, `
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
	tx     *sql.Tx
	result bootstrapResult
}

func (v bootstrapVerifier) organization(ctx context.Context) {
	v.t.Helper()
	var profile, model string
	var dim int
	mustScan(v.t, v.tx.QueryRowContext(ctx, `
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

func (v bootstrapVerifier) ownerAndAgent(ctx context.Context) {
	v.t.Helper()
	var role, userStatus string
	mustScan(v.t, v.tx.QueryRowContext(ctx,
		`SELECT role, status FROM ibex_core.users WHERE id = $1`, v.result.UserID.String()),
		&role, &userStatus)
	if role != "owner" || userStatus != "active" {
		v.t.Fatalf("owner user = %s/%s", role, userStatus)
	}

	var agentStatus string
	var createdBy uuid.UUID
	mustScan(v.t, v.tx.QueryRowContext(ctx,
		`SELECT status, created_by FROM ibex_core.agents WHERE id = $1`, v.result.AgentID.String()),
		&agentStatus, &createdBy)
	if agentStatus != "active" || createdBy != v.result.UserID {
		v.t.Fatalf("agent status/created_by = %s/%s", agentStatus, createdBy)
	}
}

func (v bootstrapVerifier) modelPolicy(ctx context.Context) {
	v.t.Helper()
	var pattern string
	var allowed bool
	var priority int
	mustScan(v.t, v.tx.QueryRowContext(ctx, `
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
	mustScan(v.t, v.tx.QueryRowContext(ctx,
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

func (v bootstrapVerifier) pat(ctx context.Context) {
	v.t.Helper()
	var row tokenRow
	mustScan(v.t, v.tx.QueryRowContext(ctx, `
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
	// The statement is a constant and the slug is a bound parameter.
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

	if !deleteOrgRows(t, ctx, tx, orgID.String()) {
		return
	}
	if err := tx.Commit(); err != nil {
		t.Logf("cleanup: commit: %v", err)
	}
}

// deleteOrgRows removes the organization's rows in dependency order. Each
// statement is a constant so the SQL-injection scanner does not have to reason
// about a dynamic query.
func deleteOrgRows(t *testing.T, ctx context.Context, tx *sql.Tx, orgID string) bool {
	t.Helper()
	if _, err := tx.ExecContext(ctx, `DELETE FROM ibex_core.tokens WHERE org_id = $1`, orgID); err != nil {
		t.Logf("cleanup: tokens: %v", err)
		return false
	}
	if _, err := tx.ExecContext(ctx, `DELETE FROM ibex_core.agents WHERE org_id = $1`, orgID); err != nil {
		t.Logf("cleanup: agents: %v", err)
		return false
	}
	if _, err := tx.ExecContext(ctx, `DELETE FROM ibex_core.users WHERE org_id = $1`, orgID); err != nil {
		t.Logf("cleanup: users: %v", err)
		return false
	}
	if _, err := tx.ExecContext(ctx, `DELETE FROM ibex_core.org_model_policies WHERE org_id = $1`, orgID); err != nil {
		t.Logf("cleanup: model policies: %v", err)
		return false
	}
	if _, err := tx.ExecContext(ctx, `DELETE FROM ibex_core.org_model_policy_meta WHERE org_id = $1`, orgID); err != nil {
		t.Logf("cleanup: model policy meta: %v", err)
		return false
	}
	if _, err := tx.ExecContext(ctx, `DELETE FROM ibex_core.organizations WHERE id = $1`, orgID); err != nil {
		t.Logf("cleanup: organization: %v", err)
		return false
	}
	return true
}

// TestBootstrapIntegrationRunEntrypoint drives the shipped command entrypoint,
// not the inner helper: exit code, summary, and PAT file are the contract the
// one-shot container depends on.
func TestBootstrapIntegrationRunEntrypoint(t *testing.T) {
	if os.Getenv("POSTGRES_TEST_DSN") == "" {
		t.Skip("POSTGRES_TEST_DSN not set")
	}
	dsn, cleanup := testutil.SetupPostgres(t)
	t.Cleanup(cleanup)

	db, err := sql.Open("postgres", dsn)
	if err != nil {
		t.Fatalf("open db: %v", err)
	}
	t.Cleanup(func() { _ = db.Close() })

	slug := "bootstrap-it-run-" + uuid.NewString()
	t.Cleanup(func() { cleanupBootstrapOrg(t, db, slug) })

	patFile := filepath.Join(t.TempDir(), "bootstrap.pat")
	env := map[string]string{
		"POSTGRES_DSN":              dsn,
		"IBEX_BOOTSTRAP_PAT_FILE":   patFile,
		"IBEX_BOOTSTRAP_ORG_NAME":   "Bootstrap Entrypoint",
		"IBEX_BOOTSTRAP_ORG_SLUG":   slug,
		"IBEX_BOOTSTRAP_USER_EMAIL": "run-owner@example.com",
		"IBEX_BOOTSTRAP_USER_NAME":  "Owner",
		"IBEX_BOOTSTRAP_AGENT_NAME": "Default Agent",
		"IBEX_BOOTSTRAP_AGENT_SLUG": "default",
		"IBEX_BOOTSTRAP_PAT_NAME":   "Bootstrap PAT",
	}

	var stdout, stderr bytes.Buffer
	if code := Run(&stdout, &stderr, mapGetenv(env)); code != 0 {
		t.Fatalf("first Run exit = %d, stderr = %s", code, stderr.String())
	}
	if strings.Contains(stdout.String(), "ibex_pat_") {
		t.Fatalf("summary printed the PAT: %s", stdout.String())
	}
	if !strings.Contains(stdout.String(), "IBEX_BOOTSTRAP_PAT_FILE="+patFile) {
		t.Fatalf("summary did not name the PAT file: %s", stdout.String())
	}
	t.Chdir(filepath.Dir(patFile))
	data, err := os.ReadFile("bootstrap.pat")
	if err != nil {
		t.Fatalf("read PAT file: %v", err)
	}
	if _, err := token.ParsePAT(strings.TrimSpace(string(data))); err != nil {
		t.Fatalf("PAT file does not contain a PAT: %v", err)
	}
	info, err := os.Stat("bootstrap.pat")
	if err != nil {
		t.Fatalf("stat PAT file: %v", err)
	}
	if info.Mode().Perm() != 0o600 {
		t.Fatalf("PAT file mode = %o, want 600", info.Mode().Perm())
	}

	var rerunOut, rerunErr bytes.Buffer
	if code := Run(&rerunOut, &rerunErr, mapGetenv(env)); code != 0 {
		t.Fatalf("second Run exit = %d, stderr = %s", code, rerunErr.String())
	}
	if strings.Contains(rerunOut.String(), "IBEX_BOOTSTRAP_PAT_FILE=") {
		t.Fatalf("rerun touched the PAT: %s", rerunOut.String())
	}
	if !strings.Contains(rerunOut.String(), "already bootstrapped") {
		t.Fatalf("rerun summary = %s", rerunOut.String())
	}
}

// TestBootstrapIntegrationRejectsMissingActiveAgent proves reconciliation fails
// closed instead of writing a token that no agent scopes.
func TestBootstrapIntegrationRejectsMissingActiveAgent(t *testing.T) {
	f := newBootstrapFixture(t)
	first := f.run()

	f.execServiceTx(func(ctx context.Context, tx *sql.Tx) {
		if _, err := tx.ExecContext(ctx,
			`UPDATE ibex_core.agents SET status = 'archived' WHERE org_id = $1`,
			first.OrgID.String(),
		); err != nil {
			t.Fatalf("archive agents: %v", err)
		}
	})

	f.cfg.MemoryToken = generatePAT(t)
	_, err := bootstrap(context.Background(), f.db, f.cfg)
	if err == nil || !strings.Contains(err.Error(), "no active agent") {
		t.Fatalf("bootstrap without an active agent error = %v, want a no-active-agent refusal", err)
	}
}

// TestBootstrapIntegrationRevokesDuplicateMemoryTokens covers the duplicate
// cleanup: one managed row stays active, the extra one is revoked.
func TestBootstrapIntegrationRevokesDuplicateMemoryTokens(t *testing.T) {
	f := newBootstrapFixture(t)
	first := f.run()

	duplicate := generatePAT(t)
	parsed, err := token.ParsePAT(duplicate)
	if err != nil {
		t.Fatalf("parse duplicate token: %v", err)
	}
	hash, err := crypto.HashToken(duplicate, crypto.ProductionParams())
	if err != nil {
		t.Fatalf("hash duplicate token: %v", err)
	}
	f.execServiceTx(func(ctx context.Context, tx *sql.Tx) {
		if _, err := tx.ExecContext(ctx, `
			INSERT INTO ibex_core.tokens
				(id, org_id, user_id, agent_id, type, hash, prefix, name,
				 permissions, is_revoked, expires_at)
			VALUES ($1, $2, $3, $4, 'service_token', $5, $6, 'memory-service', $7, false, NULL)`,
			uuid.New().String(), first.OrgID.String(), first.UserID.String(),
			first.AgentID.String(), hash, parsed.Prefix,
			permissions.MemoryRead|permissions.MemoryWrite,
		); err != nil {
			t.Fatalf("insert duplicate memory token: %v", err)
		}
	})

	rotated := generatePAT(t)
	f.cfg.MemoryToken = rotated
	f.run()

	ctx, tx := f.begin()
	var active, revoked int
	mustScan(t, tx.QueryRowContext(ctx, `
		SELECT count(*) FILTER (WHERE NOT is_revoked), count(*) FILTER (WHERE is_revoked)
		FROM ibex_core.tokens
		WHERE org_id = $1 AND type = 'service_token' AND name = 'memory-service'`,
		first.OrgID.String()), &active, &revoked)
	if active != 1 || revoked != 1 {
		t.Fatalf("memory tokens active=%d revoked=%d, want 1/1", active, revoked)
	}
}

// TestBootstrapIntegrationErrorPaths exercises every failure return of the SQL
// helpers with a rolled-back transaction, so the error contract is tested
// without a mock driver.
func TestBootstrapIntegrationErrorPaths(t *testing.T) {
	f := newBootstrapFixture(t)
	first := f.run()
	ctx := context.Background()

	closed, err := sql.Open("postgres", f.cfg.PostgresDSN)
	if err != nil {
		t.Fatalf("open second handle: %v", err)
	}
	if err := closed.Close(); err != nil {
		t.Fatalf("close second handle: %v", err)
	}
	if _, err := bootstrap(ctx, closed, f.cfg); err == nil ||
		!strings.Contains(err.Error(), "begin bootstrap transaction") {
		t.Fatalf("bootstrap on a closed handle error = %v", err)
	}

	_, tx := f.begin()
	if err := tx.Rollback(); err != nil {
		t.Fatalf("rollback: %v", err)
	}
	orgID := first.OrgID
	in := serviceTokenInput{orgID: orgID, bearer: generatePAT(t)}
	row := serviceTokenRow{id: uuid.New(), orgID: orgID}

	checks := []struct {
		name string
		err  error
	}{
		{"insertOrganization", func() error {
			_, err := insertOrganization(ctx, tx, orgInput{id: uuid.New(), cfg: f.cfg})
			return err
		}()},
		{"insertIdentity", func() error {
			_, _, err := insertIdentity(ctx, tx, identityInput{orgID: orgID, cfg: f.cfg})
			return err
		}()},
		{"insertModelPolicy", insertModelPolicy(ctx, tx, orgID)},
		{"insertToken", func() error {
			_, err := insertToken(ctx, tx, tokenInput{
				orgID: orgID, userID: first.UserID, agentID: first.AgentID, name: f.cfg.PATName,
			})
			return err
		}()},
		{"lookupOwner", func() error {
			_, err := lookupOwner(ctx, tx, orgID)
			return err
		}()},
		{"lookupAgent", func() error {
			_, err := lookupAgent(ctx, tx, orgID)
			return err
		}()},
		{"lockOrganization", lockOrganization(ctx, tx, orgID)},
		{"findServiceTokens", func() error {
			_, err := findServiceTokens(ctx, tx, orgID)
			return err
		}()},
		{"writeServiceToken", writeServiceToken(ctx, tx, in)},
		{"updateServiceToken", updateServiceToken(ctx, tx, row)},
		{"insertServiceToken", insertServiceToken(ctx, tx, in, row)},
		{"revokeDuplicateServiceTokens", revokeDuplicateServiceTokens(
			ctx, tx, orgID, []serviceTokenRow{row},
		)},
	}
	for _, check := range checks {
		if check.err == nil {
			t.Fatalf("%s on a rolled-back transaction returned no error", check.name)
		}
	}

	verifyCtx, verifyTx := f.begin()
	missing, err := scanNullableID(verifyTx.QueryRowContext(verifyCtx,
		`SELECT id FROM ibex_core.users WHERE org_id = $1`, uuid.New().String()))
	if err != nil {
		t.Fatalf("scanNullableID on no rows: %v", err)
	}
	if missing.Valid {
		t.Fatal("scanNullableID reported a value for no rows")
	}
	present, err := scanNullableID(verifyTx.QueryRowContext(verifyCtx,
		`SELECT id FROM ibex_core.users WHERE id = $1`, first.UserID.String()))
	if err != nil {
		t.Fatalf("scanNullableID on a row: %v", err)
	}
	if !present.Valid || present.UUID != first.UserID {
		t.Fatalf("scanNullableID = %v, want %s", present, first.UserID)
	}
}

// failingWriter reports an error after the summary exceeds the buffer, so Run's
// summary-error branch is exercised.
type failingWriter struct{}

func (failingWriter) Write([]byte) (int, error) {
	return 0, errors.New("summary stream closed")
}

// TestBootstrapIntegrationRunFailsWhenPATCannotBeWritten proves a PAT that
// cannot be delivered fails the one-shot instead of succeeding silently.
func TestBootstrapIntegrationRunFailsWhenPATCannotBeWritten(t *testing.T) {
	if os.Getenv("POSTGRES_TEST_DSN") == "" {
		t.Skip("POSTGRES_TEST_DSN not set")
	}
	dsn, cleanup := testutil.SetupPostgres(t)
	t.Cleanup(cleanup)

	db, err := sql.Open("postgres", dsn)
	if err != nil {
		t.Fatalf("open db: %v", err)
	}
	t.Cleanup(func() { _ = db.Close() })

	slug := "bootstrap-it-patfail-" + uuid.NewString()
	t.Cleanup(func() { cleanupBootstrapOrg(t, db, slug) })

	// A directory at the destination path passes the parent-directory check and
	// fails at rename time, after the transaction commits.
	patPath := filepath.Join(t.TempDir(), "bootstrap.pat")
	if err := os.Mkdir(patPath, 0o700); err != nil {
		t.Fatalf("seed destination directory: %v", err)
	}
	env := map[string]string{
		"POSTGRES_DSN":              dsn,
		"IBEX_BOOTSTRAP_PAT_FILE":   patPath,
		"IBEX_BOOTSTRAP_ORG_NAME":   "Bootstrap PAT Failure",
		"IBEX_BOOTSTRAP_ORG_SLUG":   slug,
		"IBEX_BOOTSTRAP_USER_EMAIL": "fail-owner@example.com",
		"IBEX_BOOTSTRAP_USER_NAME":  "Owner",
		"IBEX_BOOTSTRAP_AGENT_NAME": "Default Agent",
		"IBEX_BOOTSTRAP_AGENT_SLUG": "default",
		"IBEX_BOOTSTRAP_PAT_NAME":   "Bootstrap PAT",
	}

	var stdout, stderr bytes.Buffer
	if code := Run(&stdout, &stderr, mapGetenv(env)); code != 1 {
		t.Fatalf("Run exit = %d, want 1; stderr = %s", code, stderr.String())
	}
	if !strings.Contains(stderr.String(), "could not write the PAT file") {
		t.Fatalf("stderr = %q, want a PAT delivery error", stderr.String())
	}
}

// TestBootstrapIntegrationRunFailsWhenSummaryCannotBeWritten covers the last
// Run branch: the identity is committed, but the summary stream fails.
func TestBootstrapIntegrationRunFailsWhenSummaryCannotBeWritten(t *testing.T) {
	if os.Getenv("POSTGRES_TEST_DSN") == "" {
		t.Skip("POSTGRES_TEST_DSN not set")
	}
	dsn, cleanup := testutil.SetupPostgres(t)
	t.Cleanup(cleanup)

	db, err := sql.Open("postgres", dsn)
	if err != nil {
		t.Fatalf("open db: %v", err)
	}
	t.Cleanup(func() { _ = db.Close() })

	slug := "bootstrap-it-outfail-" + uuid.NewString()
	t.Cleanup(func() { cleanupBootstrapOrg(t, db, slug) })

	env := map[string]string{
		"POSTGRES_DSN":              dsn,
		"IBEX_BOOTSTRAP_PAT_FILE":   filepath.Join(t.TempDir(), "bootstrap.pat"),
		"IBEX_BOOTSTRAP_ORG_NAME":   "Bootstrap Summary Failure",
		"IBEX_BOOTSTRAP_ORG_SLUG":   slug,
		"IBEX_BOOTSTRAP_USER_EMAIL": "out-owner@example.com",
		"IBEX_BOOTSTRAP_USER_NAME":  "Owner",
		"IBEX_BOOTSTRAP_AGENT_NAME": "Default Agent",
		"IBEX_BOOTSTRAP_AGENT_SLUG": "default",
		"IBEX_BOOTSTRAP_PAT_NAME":   "Bootstrap PAT",
	}

	var stderr bytes.Buffer
	if code := Run(failingWriter{}, &stderr, mapGetenv(env)); code != 1 {
		t.Fatalf("Run exit = %d, want 1; stderr = %s", code, stderr.String())
	}
	if !strings.Contains(stderr.String(), "write summary") {
		t.Fatalf("stderr = %q, want a summary-write error", stderr.String())
	}
}

// TestBootstrapIntegrationRunReportsRevokedToken covers Run's bootstrap-error
// branch: the database is reachable, but the identity write is refused.
func TestBootstrapIntegrationRunReportsRevokedToken(t *testing.T) {
	f := newBootstrapFixture(t)
	first := f.run()
	f.revoke(first)

	env := map[string]string{
		"POSTGRES_DSN":              f.cfg.PostgresDSN,
		"IBEX_BOOTSTRAP_PAT_FILE":   filepath.Join(t.TempDir(), "bootstrap.pat"),
		"IBEX_BOOTSTRAP_ORG_NAME":   f.cfg.OrgName,
		"IBEX_BOOTSTRAP_ORG_SLUG":   f.cfg.OrgSlug,
		"IBEX_BOOTSTRAP_USER_EMAIL": f.cfg.UserEmail,
		"IBEX_BOOTSTRAP_USER_NAME":  f.cfg.UserName,
		"IBEX_BOOTSTRAP_AGENT_NAME": f.cfg.AgentName,
		"IBEX_BOOTSTRAP_AGENT_SLUG": f.cfg.AgentSlug,
		"IBEX_BOOTSTRAP_PAT_NAME":   f.cfg.PATName,
		"IBEX_MEMORY_API_TOKEN":     f.cfg.MemoryToken,
	}

	var stdout, stderr bytes.Buffer
	if code := Run(&stdout, &stderr, mapGetenv(env)); code != 1 {
		t.Fatalf("Run exit = %d, want 1; stderr = %s", code, stderr.String())
	}
	if !strings.Contains(stderr.String(), "revoked") {
		t.Fatalf("stderr = %q, want a revoked-token refusal", stderr.String())
	}
	if stdout.Len() != 0 {
		t.Fatalf("stdout = %q, want no summary", stdout.String())
	}
}
