//go:build integration

package bootstrap

import (
	"context"
	"database/sql"
	"errors"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/crypto"
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
	db, dsn := openIntegrationDB(t)

	cfg := newBootstrapConfig(t, dsn, uuid.NewString(), "owner@example.com")
	cfg.OrgName = "Bootstrap Integration"
	cfg.MemoryToken = generatePAT(t)
	// The compose test database is shared by the whole integration suite and
	// already holds other suites' organizations, so every fixture here is a
	// deliberate second tenant. TestBootstrapIntegrationRefusesSecondOrganization
	// clears the flag to exercise the guard itself.
	cfg.AllowSecondOrg = true

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
	// The deliberate second tenant: the guard refuses exactly this unless the
	// operator says it is intended.
	other.AllowSecondOrg = true
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
