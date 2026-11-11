//go:build integration

package postgres

import (
	"context"
	"database/sql"
	"errors"
	"strings"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/permissions"
	"github.com/google/uuid"
	"github.com/lib/pq"
)

// bootstrapMask is the only PAT mask ibex_core.bootstrap_insert_pat may write.
//
// It duplicates the literal inside the function body, which in turn duplicates
// bootstrapPermissions() in services/auth/internal/bootstrap/bootstrap.go. The
// positive-control test below calls the definer with THIS value, so a drift in
// either direction fails here instead of in production: too small and the
// bootstrap PAT loses a permission, too large and the guard rejects Go's own
// call.
var bootstrapMask = permissions.Admin | permissions.SecretUse | permissions.OperatorMetadataRead

// identityIDs are the ids one bootstrap_create_identity call is given.
type identityIDs struct {
	user, agent string
}

// newIdentityIDs returns two fresh ids.
func newIdentityIDs() identityIDs {
	return identityIDs{user: uuid.NewString(), agent: uuid.NewString()}
}

// identityCall is the argument set for ibex_core.bootstrap_create_identity.
type identityCall struct {
	orgID string
	slug  string
	ids   identityIDs
}

// patCall is the argument set for ibex_core.bootstrap_insert_pat. mask is any
// so a negative case can pass NULL, which the definer must reject like any other
// non-bootstrap value.
type patCall struct {
	orgID  string
	ids    identityIDs
	prefix string
	mask   any
}

// serviceTokenCall is the argument set for
// ibex_core.bootstrap_upsert_service_token.
type serviceTokenCall struct {
	orgID  string
	hash   string
	prefix string
}

// serviceTokenRow is the persisted subject binding a service token is asserted
// on.
type serviceTokenRow struct {
	userID, agentID, prefix string
}

// bootstrapCase is one named subtest body. Cases share one migrated fixture but
// get their own subtest-scoped clone.
type bootstrapCase struct {
	name string
	run  func(bootstrapEnv)
}

// bootstrapEnv is one subtest's fixture, test handle and context. Passing it as
// a single value keeps every helper at three parameters or fewer.
type bootstrapEnv struct {
	t   *testing.T
	f   *tenancyFixture
	ctx context.Context
}

// newBootstrapEnv binds a subtest to a clone of the shared fixture, so a helper
// that fails reports against the subtest instead of the parent test.
func newBootstrapEnv(f *tenancyFixture, t *testing.T) bootstrapEnv {
	return bootstrapEnv{t: t, f: f.sub(t), ctx: t.Context()}
}

// runBootstrapCases registers every case as a subtest over the shared fixture.
func runBootstrapCases(t *testing.T, f *tenancyFixture, cases []bootstrapCase) {
	t.Helper()
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			tc.run(newBootstrapEnv(f, t))
		})
	}
}

// seedEmptyOrg inserts an organization with no users, agents or tokens.
func (f *tenancyFixture) seedEmptyOrg(ctx context.Context, slug string) string {
	f.t.Helper()
	var id string
	if err := f.db.QueryRowContext(ctx, `
		INSERT INTO ibex_core.organizations (name, slug)
		VALUES ($1, $1) RETURNING id::text`, slug).Scan(&id); err != nil {
		f.t.Fatalf("seed empty org %s: %v", slug, err)
	}
	return id
}

// asBootstrap runs one callback in a transaction as the bootstrap login, which
// is the only role allowed to execute the seven definers.
func (f *tenancyFixture) asBootstrap(ctx context.Context, fn func(*sql.Tx) error) error {
	return f.withRole(ctx, role("ibex_bootstrap"), fn)
}

// requireGuardError asserts a guard's SQLSTATE and that its message names the
// rule. The message is the operator's only explanation of the refusal, so it is
// part of the contract rather than decoration.
func (f *tenancyFixture) requireGuardError(err error, state sqlState, rule string) {
	f.t.Helper()
	f.requireSQLSTATE(err, state)
	var pqErr *pq.Error
	if !errors.As(err, &pqErr) {
		f.t.Fatalf("expected *pq.Error, got %T: %v", err, err)
	}
	if !strings.Contains(pqErr.Message, rule) {
		f.t.Fatalf("message %q does not name the rule %q", pqErr.Message, rule)
	}
}

// countTokensFor counts an organization's token rows, optionally of one type.
func (f *tenancyFixture) countTokensFor(ctx context.Context, orgID, tokenType string) int {
	f.t.Helper()
	var n int
	if err := f.db.QueryRowContext(ctx, `
		SELECT COUNT(*) FROM ibex_core.tokens
		WHERE org_id = $1::uuid AND ($2 = '' OR type = $2)`, orgID, tokenType).Scan(&n); err != nil {
		f.t.Fatalf("count tokens: %v", err)
	}
	return n
}

// countUsersFor counts an organization's user rows.
func (f *tenancyFixture) countUsersFor(ctx context.Context, orgID string) int {
	f.t.Helper()
	var n int
	if err := f.db.QueryRowContext(ctx, `
		SELECT COUNT(*) FROM ibex_core.users WHERE org_id = $1::uuid`, orgID).Scan(&n); err != nil {
		f.t.Fatalf("count users: %v", err)
	}
	return n
}

// firstUserID returns the organization's first user id.
func (f *tenancyFixture) firstUserID(ctx context.Context, orgID string) string {
	f.t.Helper()
	var id string
	if err := f.db.QueryRowContext(ctx, `
		SELECT id::text FROM ibex_core.users WHERE org_id = $1::uuid`, orgID).Scan(&id); err != nil {
		f.t.Fatalf("read foreign user: %v", err)
	}
	return id
}

// firstAgentID returns the organization's first agent id.
func (f *tenancyFixture) firstAgentID(ctx context.Context, orgID string) string {
	f.t.Helper()
	var id string
	if err := f.db.QueryRowContext(ctx, `
		SELECT id::text FROM ibex_core.agents WHERE org_id = $1::uuid`, orgID).Scan(&id); err != nil {
		f.t.Fatalf("read foreign agent: %v", err)
	}
	return id
}

// createIdentity calls bootstrap_create_identity as the current role.
func createIdentity(ctx context.Context, tx *sql.Tx, call identityCall) error {
	_, err := tx.ExecContext(ctx, `
		SELECT ibex_core.bootstrap_create_identity(
			$1::uuid, $2::uuid, $3, $4, $5::uuid, $6, $7)`,
		call.orgID, call.ids.user, call.slug+"@example.com", call.slug,
		call.ids.agent, call.slug+" agent", call.slug)
	return err
}

// insertPAT calls bootstrap_insert_pat as the current role.
func insertPAT(ctx context.Context, tx *sql.Tx, call patCall) error {
	_, err := tx.ExecContext(ctx, `
		SELECT ibex_core.bootstrap_insert_pat(
			$1::uuid, $2::uuid, $3::uuid, $4::uuid, $5, $6, $7, $8::bigint)`,
		uuid.NewString(), call.orgID, call.ids.user, call.ids.agent,
		"hash-"+call.prefix, call.prefix, "bootstrap", call.mask)
	return err
}

// mustCreateIdentity is the positive-control call for a fresh organization.
func (e bootstrapEnv) mustCreateIdentity(call identityCall) {
	e.t.Helper()
	err := e.f.asBootstrap(e.ctx, func(tx *sql.Tx) error {
		return createIdentity(e.ctx, tx, call)
	})
	if err != nil {
		e.t.Fatalf("create identity for %s: %v", call.slug, err)
	}
}

// mustInsertPAT is the positive-control call for the bootstrap PAT.
func (e bootstrapEnv) mustInsertPAT(call patCall) {
	e.t.Helper()
	err := e.f.asBootstrap(e.ctx, func(tx *sql.Tx) error {
		return insertPAT(e.ctx, tx, call)
	})
	if err != nil {
		e.t.Fatalf("insert bootstrap PAT %s: %v", call.prefix, err)
	}
}

// bootstrapIdentity creates an empty organization plus its identity through the
// definers, so every PAT subtest starts from a legal first install.
func (e bootstrapEnv) bootstrapIdentity(slug string) (string, identityIDs) {
	e.t.Helper()
	orgID := e.f.seedEmptyOrg(e.ctx, slug)
	ids := newIdentityIDs()
	e.mustCreateIdentity(identityCall{orgID: orgID, slug: slug, ids: ids})
	return orgID, ids
}

// bootstrapTenant creates an organization plus the subject binding the
// service-token definer requires, through the definers themselves.
func (e bootstrapEnv) bootstrapTenant(slug string) tenantSeed {
	e.t.Helper()
	orgID, ids := e.bootstrapIdentity(slug)
	return tenantSeed{orgID: orgID, userID: ids.user, agentID: ids.agent}
}

// serviceTokenMask is the only mask bootstrap_upsert_service_token may write:
// permissions.MemoryRead | permissions.MemoryWrite, which is the value Go's
// writeServiceToken passes (services/auth/internal/bootstrap/bootstrap.go). A
// rotation with any other mask is refused before either branch writes.
const serviceTokenMask = permissions.MemoryRead | permissions.MemoryWrite

// upsertServiceToken calls bootstrap_upsert_service_token as ibex_bootstrap and
// returns its named outcome plus the token id (empty when the outcome carries
// none).
func (e bootstrapEnv) upsertServiceToken(call serviceTokenCall) (string, string, error) {
	e.t.Helper()
	return e.upsertServiceTokenMask(call, serviceTokenMask)
}

// upsertServiceTokenMask is upsertServiceToken with a caller-chosen mask, for
// the negative cases. mask is any so a case can pass NULL.
func (e bootstrapEnv) upsertServiceTokenMask(call serviceTokenCall, mask any) (string, string, error) {
	e.t.Helper()
	var outcome string
	var tokenID sql.NullString
	err := e.f.asBootstrap(e.ctx, func(tx *sql.Tx) error {
		return upsertServiceTokenTx(e.ctx, tx, call, mask).Scan(&outcome, &tokenID)
	})
	return outcome, tokenID.String, err
}

// upsertServiceTokenTx runs the definer inside an existing transaction, so a
// test can observe the locks it holds before COMMIT.
func upsertServiceTokenTx(ctx context.Context, tx *sql.Tx, call serviceTokenCall, mask any) *sql.Row {
	return tx.QueryRowContext(ctx, `
		SELECT outcome, token_id::text
		FROM ibex_core.bootstrap_upsert_service_token($1::uuid, $2, $3, $4::bigint)`,
		call.orgID, call.hash, call.prefix, mask)
}

// upsertServiceTokenRejected runs the definer in its own transaction and returns
// the refusal. A guard raises before any row is returned, so the scanned values
// are discarded.
func (e bootstrapEnv) upsertServiceTokenRejected(call serviceTokenCall, mask any) error {
	e.t.Helper()
	return e.f.asBootstrap(e.ctx, func(tx *sql.Tx) error {
		var outcome string
		var tokenID sql.NullString
		return upsertServiceTokenTx(e.ctx, tx, call, mask).Scan(&outcome, &tokenID)
	})
}

// beginBootstrap starts a transaction as the bootstrap login.
func (f *tenancyFixture) beginBootstrap(ctx context.Context) (*sql.Tx, error) {
	tx, err := f.db.BeginTx(ctx, nil)
	if err != nil {
		return nil, err
	}
	if err := setRole(ctx, tx, "ibex_bootstrap"); err != nil {
		_ = tx.Rollback()
		return nil, err
	}
	return tx, nil
}

// requireAdvisoryLockHeld asserts whether another session can take key now.
func (f *tenancyFixture) requireAdvisoryLockHeld(ctx context.Context, key string, wantHeld bool) {
	f.t.Helper()
	var acquired bool
	if err := f.db.QueryRowContext(ctx,
		`SELECT pg_try_advisory_xact_lock(hashtext($1::text))`, key).Scan(&acquired); err != nil {
		f.t.Fatalf("try advisory lock %q: %v", key, err)
	}
	if acquired == wantHeld {
		f.t.Fatalf("advisory lock for %q held = %v, want %v", key, !acquired, wantHeld)
	}
}

// TestTenancyBootstrapCreateIdentityGuard is the F1 lock for the identity
// definer. The attack it closes is a bootstrap caller naming an organization it
// does not own and adding an owner user to it.
func TestTenancyBootstrapCreateIdentityGuard(t *testing.T) {
	f := newTenancyFixture(t)
	runBootstrapCases(t, f, []bootstrapCase{
		{"first install succeeds", bootstrapIdentityFirstInstall},
		{"re-run refused", bootstrapIdentityRerunRefused},
		{"existing organization refused", bootstrapIdentityExistingOrgRefused},
	})
}

// bootstrapIdentityFirstInstall proves the definer's happy path on an empty
// organization.
func bootstrapIdentityFirstInstall(e bootstrapEnv) {
	orgID := e.f.seedEmptyOrg(e.ctx, "first-install")
	ids := newIdentityIDs()
	e.mustCreateIdentity(identityCall{orgID: orgID, slug: "first-install", ids: ids})
	e.assertIdentityRows(orgID, ids)
}

// bootstrapIdentityRerunRefused proves a second identity cannot be added to an
// organization that already has one.
func bootstrapIdentityRerunRefused(e bootstrapEnv) {
	orgID := e.f.seedEmptyOrg(e.ctx, "re-run-target")
	ids := newIdentityIDs()
	e.mustCreateIdentity(identityCall{orgID: orgID, slug: "re-run-target", ids: ids})
	call := identityCall{orgID: orgID, slug: "re-run-again", ids: newIdentityIDs()}
	err := e.f.asBootstrap(e.ctx, func(tx *sql.Tx) error {
		return createIdentity(e.ctx, tx, call)
	})
	e.f.requireGuardError(err, sqlState{code: "42501"}, "already has a users row")
}

// bootstrapIdentityExistingOrgRefused proves the definer refuses a victim
// organization that already has a user and leaves its row untouched.
func bootstrapIdentityExistingOrgRefused(e bootstrapEnv) {
	victim := e.f.seedTenantNamed(e.ctx, "identity-victim")
	call := identityCall{orgID: victim.orgID, slug: "identity-attacker", ids: newIdentityIDs()}
	err := e.f.asBootstrap(e.ctx, func(tx *sql.Tx) error {
		return createIdentity(e.ctx, tx, call)
	})
	e.f.requireGuardError(err, sqlState{code: "42501"}, "already has a users row")
	if users := e.f.countUsersFor(e.ctx, victim.orgID); users != 1 {
		e.t.Fatalf("victim organization has %d users, want its original 1", users)
	}
}

// assertIdentityRows checks the owner user and the agent the definer wrote.
func (e bootstrapEnv) assertIdentityRows(orgID string, ids identityIDs) {
	e.t.Helper()
	role, status := e.readOwnerUser(orgID, ids.user)
	if role != "owner" {
		e.t.Fatalf("owner user role = %s, want owner", role)
	}
	if status != "active" {
		e.t.Fatalf("owner user status = %s, want active", status)
	}
	createdBy, agentStatus := e.readAgent(orgID, ids.agent)
	if createdBy != ids.user {
		e.t.Fatalf("agent created_by = %s, want %s", createdBy, ids.user)
	}
	if agentStatus != "active" {
		e.t.Fatalf("agent status = %s, want active", agentStatus)
	}
}

// readOwnerUser returns the role and status of one user row.
func (e bootstrapEnv) readOwnerUser(orgID, userID string) (string, string) {
	e.t.Helper()
	var role, status string
	if err := e.f.db.QueryRowContext(e.ctx, `
		SELECT role, status FROM ibex_core.users
		WHERE id = $1::uuid AND org_id = $2::uuid`, userID, orgID).Scan(&role, &status); err != nil {
		e.t.Fatalf("read owner user: %v", err)
	}
	return role, status
}

// readAgent returns the created_by and status of one agent row.
func (e bootstrapEnv) readAgent(orgID, agentID string) (string, string) {
	e.t.Helper()
	var createdBy, status string
	if err := e.f.db.QueryRowContext(e.ctx, `
		SELECT created_by::text, status FROM ibex_core.agents
		WHERE id = $1::uuid AND org_id = $2::uuid`, agentID, orgID).Scan(&createdBy, &status); err != nil {
		e.t.Fatalf("read agent: %v", err)
	}
	return createdBy, status
}

// TestTenancyBootstrapPATGuard is the F1 lock for the PAT definer.
func TestTenancyBootstrapPATGuard(t *testing.T) {
	f := newTenancyFixture(t)
	runBootstrapCases(t, f, []bootstrapCase{
		{"bootstrap PAT accepted", bootstrapPATAccepted},
		{"non-bootstrap mask refused", bootstrapPATMaskRefused},
		{"second PAT refused", bootstrapPATSecondRefused},
		{"foreign owner refused", bootstrapPATForeignOwnerRefused},
		{"foreign agent refused", bootstrapPATForeignAgentRefused},
		{"bootstrapped organization refused", bootstrapPATBootstrappedOrgRefused},
	})
}

// bootstrapPATAccepted proves the exact bootstrap mask is written.
func bootstrapPATAccepted(e bootstrapEnv) {
	orgID := e.f.seedEmptyOrg(e.ctx, "pat-org")
	ids := newIdentityIDs()
	e.mustCreateIdentity(identityCall{orgID: orgID, slug: "pat-org", ids: ids})
	e.mustInsertPAT(patCall{orgID: orgID, ids: ids, prefix: "ibex_pat_first", mask: bootstrapMask})
	e.assertBootstrapPAT(orgID, "ibex_pat_first")
}

// bootstrapPATMaskRefused proves a mask that is not exactly the bootstrap grant
// is refused and writes no row.
func bootstrapPATMaskRefused(e bootstrapEnv) {
	orgID, ids := e.bootstrapIdentity("pat-mask")
	// NULL is included on purpose: the definer compares with IS DISTINCT FROM,
	// so a NULL mask must be refused instead of written as a missing value.
	for _, mask := range []any{
		permissions.Admin | permissions.SecretUse,
		bootstrapMask | permissions.OperatorRawRead,
		int64(1099511627775),
		nil,
	} {
		call := patCall{orgID: orgID, ids: ids, prefix: "ibex_pat_mask", mask: mask}
		err := e.f.asBootstrap(e.ctx, func(tx *sql.Tx) error {
			return insertPAT(e.ctx, tx, call)
		})
		e.f.requireGuardError(err, sqlState{code: "23514"}, "is not the bootstrap PAT grant")
	}
	if n := e.f.countTokensFor(e.ctx, orgID, ""); n != 0 {
		e.t.Fatalf("refused masks wrote %d tokens, want 0", n)
	}
}

// bootstrapPATSecondRefused proves an organization cannot own two PAT rows.
func bootstrapPATSecondRefused(e bootstrapEnv) {
	orgID, ids := e.bootstrapIdentity("pat-second")
	e.mustInsertPAT(patCall{orgID: orgID, ids: ids, prefix: "ibex_pat_one", mask: bootstrapMask})
	call := patCall{orgID: orgID, ids: ids, prefix: "ibex_pat_two", mask: bootstrapMask}
	err := e.f.asBootstrap(e.ctx, func(tx *sql.Tx) error {
		return insertPAT(e.ctx, tx, call)
	})
	e.f.requireGuardError(err, sqlState{code: "42501"}, "already owns a pat row")
}

// bootstrapPATForeignOwnerRefused proves the definer rejects a user that does
// not belong to the target organization.
func bootstrapPATForeignOwnerRefused(e bootstrapEnv) {
	owner, _ := e.bootstrapIdentity("pat-owner-org")
	target, targetIDs := e.bootstrapIdentity("pat-target-org")
	ids := identityIDs{user: e.f.firstUserID(e.ctx, owner), agent: targetIDs.agent}
	call := patCall{orgID: target, ids: ids, prefix: "ibex_pat_foreign", mask: bootstrapMask}
	err := e.f.asBootstrap(e.ctx, func(tx *sql.Tx) error {
		return insertPAT(e.ctx, tx, call)
	})
	e.f.requireGuardError(err, sqlState{code: "23514"}, "is not an active owner")
}

// bootstrapPATForeignAgentRefused proves the definer rejects an agent that does
// not belong to the target organization.
func bootstrapPATForeignAgentRefused(e bootstrapEnv) {
	owner, _ := e.bootstrapIdentity("pat-agent-org")
	target, targetIDs := e.bootstrapIdentity("pat-agent-target")
	ids := identityIDs{user: targetIDs.user, agent: e.f.firstAgentID(e.ctx, owner)}
	call := patCall{orgID: target, ids: ids, prefix: "ibex_pat_foreign_agent", mask: bootstrapMask}
	err := e.f.asBootstrap(e.ctx, func(tx *sql.Tx) error {
		return insertPAT(e.ctx, tx, call)
	})
	e.f.requireGuardError(err, sqlState{code: "23514"}, "is not an active agent")
}

// bootstrapPATBootstrappedOrgRefused proves an already bootstrapped victim
// organization keeps its original PAT and receives no attacker row.
func bootstrapPATBootstrappedOrgRefused(e bootstrapEnv) {
	victim := e.f.seedTenantNamed(e.ctx, "pat-victim")
	e.f.seedVictimPAT(e.ctx, victim)
	ids := identityIDs{user: victim.userID, agent: victim.agentID}
	call := patCall{orgID: victim.orgID, ids: ids, prefix: "ibex_pat_attacker", mask: bootstrapMask}
	err := e.f.asBootstrap(e.ctx, func(tx *sql.Tx) error {
		return insertPAT(e.ctx, tx, call)
	})
	e.f.requireGuardError(err, sqlState{code: "42501"}, "already owns a pat row")
	if n := e.f.countTokensFor(e.ctx, victim.orgID, "pat"); n != 1 {
		e.t.Fatalf("victim organization has %d pat rows, want its original 1", n)
	}
}

// assertBootstrapPAT checks the row the definer wrote.
func (e bootstrapEnv) assertBootstrapPAT(orgID, prefix string) {
	e.t.Helper()
	var tokenType string
	var mask int64
	var revoked bool
	var expiresAt sql.NullTime
	if err := e.f.db.QueryRowContext(e.ctx, `
		SELECT type, permissions, is_revoked, expires_at FROM ibex_core.tokens
		WHERE org_id = $1::uuid AND prefix = $2`, orgID, prefix).
		Scan(&tokenType, &mask, &revoked, &expiresAt); err != nil {
		e.t.Fatalf("read bootstrap PAT: %v", err)
	}
	if tokenType != "pat" {
		e.t.Fatalf("type = %s, want pat", tokenType)
	}
	if mask != bootstrapMask {
		e.t.Fatalf("permissions = %d, want the bootstrap mask %d", mask, bootstrapMask)
	}
	if revoked {
		e.t.Fatal("bootstrap PAT is revoked, want active")
	}
	if expiresAt.Valid {
		e.t.Fatalf("bootstrap PAT expires_at = %v, want no expiry", expiresAt.Time)
	}
}

// seedVictimPAT gives an already bootstrapped organization its own PAT, which is
// the state every production tenant is in.
func (f *tenancyFixture) seedVictimPAT(ctx context.Context, victim tenantSeed) {
	f.t.Helper()
	if _, err := f.db.ExecContext(ctx, `
		INSERT INTO ibex_core.tokens (org_id, user_id, agent_id, type, hash, prefix, name, permissions)
		VALUES ($1::uuid, $2::uuid, $3::uuid, 'pat', $4, $5, 'victim bootstrap', $6)`,
		victim.orgID, victim.userID, victim.agentID, "hash-victim-"+victim.orgID,
		"ibex_pat_victim_"+victim.orgID[:8], bootstrapMask); err != nil {
		f.t.Fatalf("seed victim PAT: %v", err)
	}
}

// TestTenancyBootstrapServiceTokenGuard is the F1 lock for the service-token
// definer: an organization with no active owner or no active agent must be
// refused instead of receiving a credential with NULL subjects.
func TestTenancyBootstrapServiceTokenGuard(t *testing.T) {
	f := newTenancyFixture(t)
	runBootstrapCases(t, f, []bootstrapCase{
		{"organization without subjects refused", bootstrapServiceTokenNoSubjectsRefused},
		{"non-service mask refused", bootstrapServiceTokenMaskRefused},
		{"inserted then rotated", bootstrapServiceTokenRotates},
		{"own prefix re-run is not a conflict", bootstrapServiceTokenOwnPrefixRerun},
		{"another organization's prefix refused", bootstrapServiceTokenForeignPrefixRefused},
	})
}

// bootstrapServiceTokenMaskRefused proves the rotation path rejects every mask
// but MemoryRead | MemoryWrite before it writes. Without the guard the UPDATE
// branch wrote p_permissions verbatim, so a caller could rotate the
// organization's service credential into a full-admin grant.
func bootstrapServiceTokenMaskRefused(e bootstrapEnv) {
	tenant := e.bootstrapTenant("service-token-mask")
	for _, mask := range []any{
		int64(permissions.ProxyChatCompletion),
		int64(permissions.Admin),
		int64(serviceTokenMask | permissions.MemoryDelete),
		nil,
	} {
		call := serviceTokenCall{orgID: tenant.orgID, hash: "hash-mask", prefix: "ibex_pat_service_mask"}
		e.f.requireGuardError(e.upsertServiceTokenRejected(call, mask), sqlState{code: "23514"}, "is not the memory-service grant")
	}
	if n := e.f.countTokensFor(e.ctx, tenant.orgID, ""); n != 0 {
		e.t.Fatalf("refused masks wrote %d tokens, want 0", n)
	}
}

// bootstrapServiceTokenNoSubjectsRefused proves an organization with no owner
// or agent is refused and writes no token.
func bootstrapServiceTokenNoSubjectsRefused(e bootstrapEnv) {
	orgID := e.f.seedEmptyOrg(e.ctx, "token-no-subjects")
	call := serviceTokenCall{orgID: orgID, hash: "hash-no-subjects", prefix: "ibex_pat_no_subjects"}
	outcome, tokenID, err := e.upsertServiceToken(call)
	if err == nil {
		e.t.Fatalf("expected a refusal, got outcome %q id %q", outcome, tokenID)
	}
	e.f.requireGuardError(err, sqlState{code: "23514"}, "no active owner user")
	if n := e.f.countTokensFor(e.ctx, orgID, ""); n != 0 {
		e.t.Fatalf("refused upsert wrote %d tokens, want 0", n)
	}
}

// bootstrapServiceTokenRotates proves the first call inserts and the re-run
// rotates the same row, keeping the subject binding.
func bootstrapServiceTokenRotates(e bootstrapEnv) {
	tenant := e.bootstrapTenant("token-rotates")
	e.assertServiceTokenInserted(tenant)
	e.assertServiceTokenRotated(tenant)
}

// bootstrapServiceTokenOwnPrefixRerun proves the same operator re-run is an
// update, not a conflict with the caller's own prefix.
func bootstrapServiceTokenOwnPrefixRerun(e bootstrapEnv) {
	tenant := e.bootstrapTenant("token-rerun")
	call := serviceTokenCall{orgID: tenant.orgID, hash: "hash-rerun", prefix: "ibex_pat_rerun"}
	tokenID := e.mustUpsertInserted(call, "first call")
	replay := serviceTokenCall{orgID: tenant.orgID, hash: "hash-rerun", prefix: "ibex_pat_rerun"}
	e.assertServiceTokenReplay(replay, "re-run", tokenID)
}

// bootstrapServiceTokenForeignPrefixRefused proves another organization's
// prefix is reported as a conflict and writes no row.
func bootstrapServiceTokenForeignPrefixRefused(e bootstrapEnv) {
	holder := e.f.seedTenantNamed(e.ctx, "prefix-holder")
	e.f.seedTokenFor(e.ctx, holder.orgID, tokenSeed{prefix: "ibex_pat_held", hash: "hash-held"})
	tenant := e.bootstrapTenant("prefix-taker")
	call := serviceTokenCall{orgID: tenant.orgID, hash: "hash-taker", prefix: "ibex_pat_held"}
	outcome, tokenID, err := e.upsertServiceToken(call)
	if err != nil {
		e.t.Fatalf("prefix conflict: %v", err)
	}
	if outcome != "prefix_conflict" {
		e.t.Fatalf("outcome = %q, want prefix_conflict", outcome)
	}
	if tokenID != "" {
		e.t.Fatalf("token id = %q, want empty", tokenID)
	}
	if n := e.f.countTokensFor(e.ctx, tenant.orgID, ""); n != 0 {
		e.t.Fatalf("conflicting org wrote %d tokens, want 0", n)
	}
}

// assertServiceTokenInserted covers the first call and its subject binding.
func (e bootstrapEnv) assertServiceTokenInserted(tenant tenantSeed) {
	e.t.Helper()
	call := serviceTokenCall{orgID: tenant.orgID, hash: "hash-first", prefix: "ibex_pat_service_first"}
	tokenID := e.mustUpsertInserted(call, "insert service token")
	e.assertServiceTokenSubjects(tokenID, tenant, "ibex_pat_service_first")
}

// assertServiceTokenRotated covers the re-run: same row, new hash and prefix,
// subjects still bound.
func (e bootstrapEnv) assertServiceTokenRotated(tenant tenantSeed) {
	e.t.Helper()
	before := e.f.serviceTokenID(e.ctx, tenant.orgID)
	call := serviceTokenCall{orgID: tenant.orgID, hash: "hash-second", prefix: "ibex_pat_service_second"}
	outcome, tokenID, err := e.upsertServiceToken(call)
	if err != nil {
		e.t.Fatalf("rotate service token: %v", err)
	}
	if outcome != "updated" {
		e.t.Fatalf("outcome = %q, want updated", outcome)
	}
	if tokenID != before {
		e.t.Fatalf("token id = %q, want updated on %s", tokenID, before)
	}
	e.assertServiceTokenSubjects(before, tenant, "ibex_pat_service_second")
}

// assertServiceTokenReplay covers the same-prefix re-run: it updates the same
// row instead of reporting a conflict with the caller's own organization.
func (e bootstrapEnv) assertServiceTokenReplay(call serviceTokenCall, label, wantID string) {
	e.t.Helper()
	outcome, tokenID, err := e.upsertServiceToken(call)
	if err != nil {
		e.t.Fatalf("%s: %v", label, err)
	}
	if outcome != "updated" {
		e.t.Fatalf("%s outcome = %q, want updated", label, outcome)
	}
	if tokenID != wantID {
		e.t.Fatalf("%s token id = %q, want updated on %s", label, tokenID, wantID)
	}
}

// mustUpsertInserted asserts an insert outcome with a non-empty id and returns
// the id.
func (e bootstrapEnv) mustUpsertInserted(call serviceTokenCall, label string) string {
	e.t.Helper()
	outcome, tokenID, err := e.upsertServiceToken(call)
	if err != nil {
		e.t.Fatalf("%s: %v", label, err)
	}
	if outcome != "inserted" {
		e.t.Fatalf("%s outcome = %q, want inserted", label, outcome)
	}
	if tokenID == "" {
		e.t.Fatalf("%s returned no token id", label)
	}
	return tokenID
}

// assertServiceTokenSubjects checks the row is bound, not NULL, and carries the
// prefix the rotation wrote.
func (e bootstrapEnv) assertServiceTokenSubjects(tokenID string, tenant tenantSeed, prefix string) {
	e.t.Helper()
	row := e.readServiceToken(tokenID)
	if row.userID != tenant.userID {
		e.t.Fatalf("service token user id = %s, want %s", row.userID, tenant.userID)
	}
	if row.agentID != tenant.agentID {
		e.t.Fatalf("service token agent id = %s, want %s", row.agentID, tenant.agentID)
	}
	if row.prefix != prefix {
		e.t.Fatalf("prefix = %s, want %s", row.prefix, prefix)
	}
}

// readServiceToken returns one token row's subject binding and prefix.
func (e bootstrapEnv) readServiceToken(tokenID string) serviceTokenRow {
	e.t.Helper()
	var row serviceTokenRow
	if err := e.f.db.QueryRowContext(e.ctx, `
		SELECT user_id::text, agent_id::text, prefix FROM ibex_core.tokens
		WHERE id = $1::uuid`, tokenID).Scan(&row.userID, &row.agentID, &row.prefix); err != nil {
		e.t.Fatalf("read service token: %v", err)
	}
	return row
}

// serviceTokenID returns the organization's managed memory-service token id.
func (f *tenancyFixture) serviceTokenID(ctx context.Context, orgID string) string {
	f.t.Helper()
	var id string
	if err := f.db.QueryRowContext(ctx, `
		SELECT id::text FROM ibex_core.tokens
		WHERE org_id = $1::uuid AND type = 'service_token' AND name = 'memory-service'`,
		orgID).Scan(&id); err != nil {
		f.t.Fatalf("read service token id: %v", err)
	}
	return id
}

// seedTokenFor inserts one token for an explicit organization.
func (f *tenancyFixture) seedTokenFor(ctx context.Context, orgID string, seed tokenSeed) string {
	f.t.Helper()
	var id string
	if err := f.db.QueryRowContext(ctx, `
		INSERT INTO ibex_core.tokens (org_id, type, hash, prefix, name, permissions)
		VALUES ($1::uuid, 'pat', $2, $3, 'holder', 0) RETURNING id::text`,
		orgID, seed.hash, seed.prefix).Scan(&id); err != nil {
		f.t.Fatalf("seed token %s: %v", seed.prefix, err)
	}
	return id
}

// TestTenancyBootstrapSerializesPerOrg proves the org-scoped check-then-write
// runs under a per-organization advisory lock and that the prefix lock is taken
// after it.
//
// bootstrap_create_identity's "no users row" EXISTS and its two INSERTs are not
// atomic on their own: two concurrent calls both see no row and both insert. The
// lock closes that window, and both definers take org then prefix so they cannot
// deadlock. Dropping either PERFORM (or swapping the order) fails here.
func TestTenancyBootstrapSerializesPerOrg(t *testing.T) {
	f := newTenancyFixture(t)
	ctx := t.Context()
	orgID := f.seedEmptyOrg(ctx, "serialized-org")
	tx, err := f.beginBootstrap(ctx)
	if err != nil {
		t.Fatalf("begin bootstrap transaction: %v", err)
	}
	defer func() { _ = tx.Rollback() }()

	ids := newIdentityIDs()
	if err := createIdentity(ctx, tx, identityCall{orgID: orgID, slug: "serialized-org", ids: ids}); err != nil {
		t.Fatalf("create identity: %v", err)
	}
	f.requireAdvisoryLockHeld(ctx, orgID, true)

	call := serviceTokenCall{orgID: orgID, hash: "hash-lock", prefix: "ibex_pat_lock"}
	var outcome string
	var tokenID sql.NullString
	if err := upsertServiceTokenTx(ctx, tx, call, serviceTokenMask).Scan(&outcome, &tokenID); err != nil {
		t.Fatalf("upsert service token: %v", err)
	}
	f.requireAdvisoryLockHeld(ctx, orgID, true)
	f.requireAdvisoryLockHeld(ctx, call.prefix, true)

	if err := tx.Commit(); err != nil {
		t.Fatalf("commit: %v", err)
	}
	f.requireAdvisoryLockHeld(ctx, orgID, false)
	f.requireAdvisoryLockHeld(ctx, call.prefix, false)
}
