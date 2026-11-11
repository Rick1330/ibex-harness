//go:build integration

package bootstrap

import (
	"bytes"
	"context"
	"database/sql"
	"errors"
	"net/url"
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
		OrgSlug:     uuid.NewString(),
		UserEmail:   "owner@example.com",
		UserName:    "Owner",
		AgentName:   "Default Agent",
		AgentSlug:   "default",
		PATName:     "Bootstrap PAT",
		PATFile:     filepath.Join(t.TempDir(), "bootstrap.pat"),
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
	other.OrgSlug = uuid.NewString()
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
			WHERE agent_id = $1 AND org_id = $2 AND type = 'service_token'`,
			result.AgentID.String(), result.OrgID.String()); err != nil {
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
		WHERE agent_id = $1 AND org_id = $2 AND type = 'service_token'`,
		result.AgentID.String(), result.OrgID.String(),
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
		WHERE agent_id = $1 AND org_id = $2 AND type = 'service_token'`,
		result.AgentID.String(), result.OrgID.String(),
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
		`SELECT role, status FROM ibex_core.users WHERE id = $1 AND org_id = $2`,
		v.result.UserID.String(), v.result.OrgID.String()),
		&role, &userStatus)
	if role != "owner" || userStatus != "active" {
		v.t.Fatalf("owner user = %s/%s", role, userStatus)
	}

	var agentStatus string
	var createdBy uuid.UUID
	mustScan(v.t, v.tx.QueryRowContext(ctx,
		`SELECT status, created_by FROM ibex_core.agents WHERE id = $1 AND org_id = $2`,
		v.result.AgentID.String(), v.result.OrgID.String()),
		&agentStatus, &createdBy)
	if agentStatus != "active" || createdBy != v.result.UserID {
		v.t.Fatalf("agent status/created_by = %s/%s", agentStatus, createdBy)
	}
}

// modelPolicy asserts the create path left exactly one allow-all policy and one
// epoch: both are written by bootstrap_upsert_organization, in the statement
// that creates the organization, so no bootstrap call can add a second pair.
func (v bootstrapVerifier) modelPolicy(ctx context.Context) {
	v.t.Helper()
	v.assertFallbackPolicy(ctx)
	v.assertPolicyEpoch(ctx)
}

// assertFallbackPolicy checks the organization holds one policy row: the
// allow-all fallback at priority 1000.
func (v bootstrapVerifier) assertFallbackPolicy(ctx context.Context) {
	v.t.Helper()
	var rows int
	mustScan(v.t, v.tx.QueryRowContext(ctx,
		`SELECT COUNT(*) FROM ibex_core.org_model_policies WHERE org_id = $1`, v.result.OrgID.String()),
		&rows)
	if rows != 1 {
		v.t.Fatalf("model policy rows = %d, want exactly the fallback", rows)
	}

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
}

// assertPolicyEpoch checks the organization holds one epoch row, at 1.
func (v bootstrapVerifier) assertPolicyEpoch(ctx context.Context) {
	v.t.Helper()
	var rows int
	mustScan(v.t, v.tx.QueryRowContext(ctx,
		`SELECT COUNT(*) FROM ibex_core.org_model_policy_meta WHERE org_id = $1`, v.result.OrgID.String()),
		&rows)
	if rows != 1 {
		v.t.Fatalf("model policy epoch rows = %d, want 1", rows)
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

// openCapabilityDSN returns dsn rewritten to connect as one capability login.
// Provision still reads the owner credential from the original DSN, so only the
// pool under test carries the capability login.
func openCapabilityDSN(t *testing.T, dsn, login, password string) string {
	t.Helper()
	parsed, err := url.Parse(dsn)
	if err != nil {
		t.Fatalf("parse test DSN: %v", err)
	}
	parsed.User = url.UserPassword(login, password)
	return parsed.String()
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
type entrypointRun struct {
	code   int
	stdout string
	stderr string
}

type entrypointFixture struct {
	env     map[string]string
	patFile string
	db      *sql.DB
	slug    string
}

// newEntrypointFixture provisions a database and the environment the shipped
// command expects, with a PAT path inside the test's own directory.
func newEntrypointFixture(t *testing.T, orgName string) entrypointFixture {
	t.Helper()
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

	slug := uuid.NewString()
	t.Cleanup(func() { cleanupBootstrapOrg(t, db, slug) })

	patFile := filepath.Join(t.TempDir(), "bootstrap.pat")
	env := map[string]string{
		"POSTGRES_DSN":              dsn,
		"IBEX_BOOTSTRAP_PAT_FILE":   patFile,
		"IBEX_BOOTSTRAP_ORG_NAME":   orgName,
		"IBEX_BOOTSTRAP_ORG_SLUG":   slug,
		"IBEX_BOOTSTRAP_USER_EMAIL": "run-owner@example.com",
		"IBEX_BOOTSTRAP_USER_NAME":  "Owner",
		"IBEX_BOOTSTRAP_AGENT_NAME": "Default Agent",
		"IBEX_BOOTSTRAP_AGENT_SLUG": "default",
		"IBEX_BOOTSTRAP_PAT_NAME":   "Bootstrap PAT",
	}
	return entrypointFixture{env: env, patFile: patFile, db: db, slug: slug}
}

func runEntrypoint(t *testing.T, env map[string]string) entrypointRun {
	t.Helper()
	var stdout, stderr bytes.Buffer
	code := Run(&stdout, &stderr, mapGetenv(env))
	return entrypointRun{code: code, stdout: stdout.String(), stderr: stderr.String()}
}

func requireRunSucceeded(t *testing.T, run entrypointRun) {
	t.Helper()
	if run.code != 0 {
		t.Fatalf("Run exit = %d, stderr = %s", run.code, run.stderr)
	}
}

func assertSummaryNamesPATFile(t *testing.T, stdout, patFile string) {
	t.Helper()
	if strings.Contains(stdout, "ibex_pat_") {
		t.Fatalf("summary printed the PAT: %s", stdout)
	}
	if !strings.Contains(stdout, "IBEX_BOOTSTRAP_PAT_FILE="+patFile) {
		t.Fatalf("summary did not name the PAT file: %s", stdout)
	}
}

func readPATFile(t *testing.T, patFile string) []byte {
	t.Helper()
	t.Chdir(filepath.Dir(patFile))
	data, err := os.ReadFile("bootstrap.pat")
	if err != nil {
		t.Fatalf("read PAT file: %v", err)
	}
	return data
}

func assertPATFileValid(t *testing.T, patFile string) []byte {
	t.Helper()
	data := readPATFile(t, patFile)
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
	return data
}

// assertPATMatchesStoredHash verifies the delivered bearer against the committed
// admin-token hash, not just its shape.
func assertPATMatchesStoredHash(t *testing.T, db *sql.DB, slug, bearer string) {
	t.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), verifyTimeout)
	defer cancel()
	var hash string
	if err := db.QueryRowContext(ctx, `
		SELECT t.hash FROM ibex_core.tokens t
		INNER JOIN ibex_core.organizations o ON o.id = t.org_id
		WHERE o.slug = $1 AND t.type = 'pat' AND t.is_revoked = false`,
		slug,
	).Scan(&hash); err != nil {
		t.Fatalf("read stored PAT hash: %v", err)
	}
	ok, err := crypto.VerifyToken(bearer, hash, crypto.ProductionParams())
	if err != nil {
		t.Fatalf("verify delivered PAT: %v", err)
	}
	if !ok {
		t.Fatal("delivered PAT does not match the stored hash")
	}
}

// TestBootstrapIntegrationRunEntrypoint drives the shipped command entrypoint,
// not the inner helper: exit code, summary, and PAT file are the contract the
// one-shot container depends on.
func TestBootstrapIntegrationRunEntrypoint(t *testing.T) {
	f := newEntrypointFixture(t, "Bootstrap Entrypoint")

	run := runEntrypoint(t, f.env)
	requireRunSucceeded(t, run)
	assertSummaryNamesPATFile(t, run.stdout, f.patFile)
	data := assertPATFileValid(t, f.patFile)
	assertPATMatchesStoredHash(t, f.db, f.slug, strings.TrimSpace(string(data)))
}

// TestBootstrapIntegrationRunEntrypointRerun proves a second run reconciles
// without issuing or touching a PAT.
func TestBootstrapIntegrationRunEntrypointRerun(t *testing.T) {
	f := newEntrypointFixture(t, "Bootstrap Entrypoint Rerun")

	requireRunSucceeded(t, runEntrypoint(t, f.env))
	before := readPATFile(t, f.patFile)

	rerun := runEntrypoint(t, f.env)
	requireRunSucceeded(t, rerun)
	if strings.Contains(rerun.stdout, "IBEX_BOOTSTRAP_PAT_FILE=") {
		t.Fatalf("rerun touched the PAT: %s", rerun.stdout)
	}
	if !strings.Contains(rerun.stdout, "already bootstrapped") {
		t.Fatalf("rerun summary = %s", rerun.stdout)
	}
	after := readPATFile(t, f.patFile)
	if !bytes.Equal(before, after) {
		t.Fatal("rerun changed the delivered PAT file")
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

// TestBootstrapIntegrationRejectsSoftDeletedSlug proves a soft-deleted
// organization is reported by name instead of surfacing a bare no-rows error.
func TestBootstrapIntegrationRejectsSoftDeletedSlug(t *testing.T) {
	f := newBootstrapFixture(t)
	first := f.run()

	f.execServiceTx(func(ctx context.Context, tx *sql.Tx) {
		if _, err := tx.ExecContext(ctx,
			`UPDATE ibex_core.organizations SET deleted_at = NOW() WHERE id = $1`,
			first.OrgID.String(),
		); err != nil {
			t.Fatalf("soft-delete organization: %v", err)
		}
	})

	_, err := bootstrap(context.Background(), f.db, f.cfg)
	if err == nil || !strings.Contains(err.Error(), "soft-deleted") {
		t.Fatalf("bootstrap on a soft-deleted slug error = %v, want a soft-deleted refusal", err)
	}
}

// TestBootstrapIntegrationClosedDatabase covers the transaction-start failure.
func TestBootstrapIntegrationClosedDatabase(t *testing.T) {
	f := newBootstrapFixture(t)

	closed, err := sql.Open("postgres", f.cfg.PostgresDSN)
	if err != nil {
		t.Fatalf("open second handle: %v", err)
	}
	if err := closed.Close(); err != nil {
		t.Fatalf("close second handle: %v", err)
	}
	_, err = bootstrap(context.Background(), closed, f.cfg)
	if err == nil || !strings.Contains(err.Error(), "begin bootstrap transaction") {
		t.Fatalf("bootstrap on a closed handle error = %v", err)
	}
}

// TestBootstrapIntegrationHelperErrorContract exercises every failure return of
// the definer helpers with a rolled-back transaction, so the error contract is
// tested without a mock driver.
func TestBootstrapIntegrationHelperErrorContract(t *testing.T) {
	f := newBootstrapFixture(t)
	first := f.run()
	ctx := context.Background()

	_, tx := f.begin()
	if err := tx.Rollback(); err != nil {
		t.Fatalf("rollback: %v", err)
	}
	orgID := first.OrgID

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
		{"insertToken", func() error {
			_, err := insertToken(ctx, tx, tokenInput{
				orgID: orgID, userID: first.UserID, agentID: first.AgentID, name: f.cfg.PATName,
			})
			return err
		}()},
		{"lookupSubjects", func() error {
			_, err := lookupSubjects(ctx, tx, orgID)
			return err
		}()},
		{"lockOrganization", func() error {
			_, err := lockOrganization(ctx, tx, orgID)
			return err
		}()},
		{"writeServiceToken", writeServiceToken(ctx, tx, serviceTokenInput{
			orgID: orgID, bearer: generatePAT(t),
		})},
	}
	for _, check := range checks {
		if check.err == nil {
			t.Fatalf("%s on a rolled-back transaction returned no error", check.name)
		}
	}
}

// TestBootstrapIntegrationAsBootstrapLogin is the positive control for
// migration 000069: the command must work when it connects as the
// least-privilege ibex_bootstrap login, which holds EXECUTE on the six
// definers and no table privilege at all. The owner pool is used only to
// provision the logins and to verify the rows afterwards, because a superuser
// bypasses RLS and would make a missing column grant invisible.
func TestBootstrapIntegrationAsBootstrapLogin(t *testing.T) {
	if os.Getenv("POSTGRES_TEST_DSN") == "" {
		t.Skip("POSTGRES_TEST_DSN not set")
	}
	dsn, cleanup := testutil.SetupPostgres(t)
	t.Cleanup(cleanup)

	ownerDB := testutil.OpenDB(t, dsn)
	t.Cleanup(func() { _ = ownerDB.Close() })

	cfg := bootstrapConfig{
		PostgresDSN: openCapabilityDSN(t, dsn, "ibex_bootstrap", testutil.BootstrapLoginTestPassword),
		OrgName:     "Bootstrap As Login",
		OrgSlug:     uuid.NewString(),
		UserEmail:   "login-owner@example.com",
		UserName:    "Owner",
		AgentName:   "Default Agent",
		AgentSlug:   "default",
		PATName:     "Bootstrap PAT",
		PATFile:     filepath.Join(t.TempDir(), "bootstrap.pat"),
		MemoryToken: generatePAT(t),
	}
	t.Cleanup(func() { cleanupBootstrapOrg(t, ownerDB, cfg.OrgSlug) })

	testutil.ProvisionCapabilityLogins(t, dsn)
	bootstrapDB, err := sql.Open("postgres", cfg.PostgresDSN)
	if err != nil {
		t.Fatalf("open bootstrap pool: %v", err)
	}
	t.Cleanup(func() { _ = bootstrapDB.Close() })

	first, err := bootstrap(context.Background(), bootstrapDB, cfg)
	if err != nil {
		t.Fatalf("bootstrap as ibex_bootstrap: %v", err)
	}
	assertFirstRun(t, first)

	ctx, tx := openServiceTx(t, ownerDB)
	v := bootstrapVerifier{t: t, tx: tx, result: first}
	v.organization(ctx)
	v.ownerAndAgent(ctx)
	v.modelPolicy(ctx)
	v.pat(ctx)
	v.memoryToken(ctx, cfg.MemoryToken)

	// A re-run must reach the reconcile path, which locks the organization and
	// re-reads the subjects through the definers.
	rerun, err := bootstrap(context.Background(), bootstrapDB, cfg)
	if err != nil {
		t.Fatalf("rerun as ibex_bootstrap: %v", err)
	}
	assertAlreadyBootstrapped(t, rerun, true)
}

// failingWriter reports an error after the summary exceeds the buffer, so Run's
// summary-error branch is exercised.
type failingWriter struct{}

func (failingWriter) Write([]byte) (int, error) {
	return 0, errors.New("summary stream closed")
}

// TestBootstrapIntegrationRunFailsWhenPATCannotBeWritten proves a PAT that
// cannot be delivered fails the one-shot and rolls the identity back, so a
// rerun issues a fresh PAT instead of leaving an organization with no
// recoverable credential.
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

	slug := uuid.NewString()
	t.Cleanup(func() { cleanupBootstrapOrg(t, db, slug) })

	// A directory at the destination path passes the parent-directory check and
	// fails at rename time, before the transaction commits.
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
	if !strings.Contains(stderr.String(), "could not write the admin PAT") {
		t.Fatalf("stderr = %q, want a PAT delivery error", stderr.String())
	}

	ctx, tx := openServiceTx(t, db)
	var count int
	if err := tx.QueryRowContext(ctx,
		`SELECT count(*) FROM ibex_core.organizations WHERE slug = $1`, slug,
	).Scan(&count); err != nil {
		t.Fatalf("count organizations: %v", err)
	}
	if count != 0 {
		t.Fatalf("organizations with slug %q = %d, want 0 after a delivery failure", slug, count)
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

	slug := uuid.NewString()
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

// TestBootstrapIntegrationRejectsReusedMemoryToken proves one bearer cannot be
// bound to two organizations. The validator resolves a bearer by prefix alone,
// so a shared value would make the organizations indistinguishable.
func TestBootstrapIntegrationRejectsReusedMemoryToken(t *testing.T) {
	f := newBootstrapFixture(t)
	f.run()

	other := f.cfg
	other.OrgSlug = uuid.NewString()
	other.UserEmail = "reused-token@example.com"
	t.Cleanup(func() { cleanupBootstrapOrg(t, f.db, other.OrgSlug) })

	_, err := bootstrap(context.Background(), f.db, other)
	if err == nil || !strings.Contains(err.Error(), "already bound to another organization") {
		t.Fatalf("bootstrap with a reused memory token error = %v", err)
	}

	var count int
	if err := f.db.QueryRowContext(context.Background(),
		`SELECT count(*) FROM ibex_core.organizations WHERE slug = $1`, other.OrgSlug,
	).Scan(&count); err != nil {
		t.Fatalf("count organizations: %v", err)
	}
	if count != 0 {
		t.Fatalf("organizations with slug %q = %d, want 0 after the refusal", other.OrgSlug, count)
	}
}

// TestBootstrapIntegrationBindsActiveReplacementAgent proves reconciliation
// selects an active agent when the original one is archived, instead of
// failing or binding the stale row.
func TestBootstrapIntegrationBindsActiveReplacementAgent(t *testing.T) {
	f := newBootstrapFixture(t)
	first := f.run()

	replacement := uuid.New()
	f.execServiceTx(func(ctx context.Context, tx *sql.Tx) {
		if _, err := tx.ExecContext(ctx,
			`UPDATE ibex_core.agents SET status = 'archived' WHERE org_id = $1`,
			first.OrgID.String(),
		); err != nil {
			t.Fatalf("archive agents: %v", err)
		}
		if _, err := tx.ExecContext(ctx, `
			INSERT INTO ibex_core.agents (id, org_id, created_by, name, slug, status)
			VALUES ($1, $2, $3, 'Replacement Agent', 'replacement', 'active')`,
			replacement.String(), first.OrgID.String(), first.UserID.String(),
		); err != nil {
			t.Fatalf("insert replacement agent: %v", err)
		}
	})

	f.cfg.MemoryToken = generatePAT(t)
	f.run()

	ctx, tx := f.begin()
	var bound uuid.UUID
	if err := tx.QueryRowContext(ctx, `
		SELECT agent_id FROM ibex_core.tokens
		WHERE org_id = $1 AND type = 'service_token' AND name = 'memory-service' AND NOT is_revoked`,
		first.OrgID.String(),
	).Scan(&bound); err != nil {
		t.Fatalf("read bound agent: %v", err)
	}
	if bound != replacement {
		t.Fatalf("memory token bound to %s, want the active replacement %s", bound, replacement)
	}
}
