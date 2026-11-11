//go:build integration

package postgres

import (
	"context"
	"database/sql"
	"errors"
	"strconv"
	"strings"
	"testing"
	"time"

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

// modelPolicyRow is the wildcard fallback and the epoch written with it.
type modelPolicyRow struct {
	allowed  bool
	priority int
	epoch    int
}

// modelPolicySeed is one policy row a test seeds.
type modelPolicySeed struct {
	pattern  string
	allowed  bool
	priority int
}

// serviceTokenRow is the persisted state a service token is asserted on: the
// subject binding, the prefix, and the fields a rejected rotation must not
// change.
type serviceTokenRow struct {
	userID, agentID, prefix, hash string
	permissions                   int64
}

// managedTokenSeed is one managed memory-service row seeded directly by a test,
// with an explicit age so the definer's oldest-row choice is deterministic
// rather than a race on created_at ties.
type managedTokenSeed struct {
	hash, prefix string
	age          time.Duration
}

// bootstrapCase is one named subtest body. Cases share one migrated fixture but
// get their own subtest-scoped clone.
type bootstrapCase struct {
	name string
	run  func(bootstrapEnv)
}

// bootstrapEnv is one subtest's fixture and test handle. Passing it as a single
// value keeps every helper at three parameters or fewer. The context is not
// stored here: each helper takes it as a parameter, and the subtest handle is
// the one source for it (t.Context()).
type bootstrapEnv struct {
	t *testing.T
	f *tenancyFixture
}

// newBootstrapEnv binds a subtest to a clone of the shared fixture, so a helper
// that fails reports against the subtest instead of the parent test.
func newBootstrapEnv(f *tenancyFixture, t *testing.T) bootstrapEnv {
	return bootstrapEnv{t: t, f: f.sub(t)}
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

// seedOwnerOnlyOrg inserts an organization with an active owner and no agent.
func (f *tenancyFixture) seedOwnerOnlyOrg(ctx context.Context, slug string) tenantSeed {
	f.t.Helper()
	seed := tenantSeed{orgID: f.seedEmptyOrg(ctx, slug)}
	seed.userID = f.seedUser(ctx, seed.orgID, slug, "owner")
	return seed
}

// seedAgentOnlyOrg inserts an organization with an active agent and no user.
func (f *tenancyFixture) seedAgentOnlyOrg(ctx context.Context, slug string) tenantSeed {
	f.t.Helper()
	seed := tenantSeed{orgID: f.seedEmptyOrg(ctx, slug)}
	seed.agentID = f.seedAgent(ctx, seed.orgID, slug, sql.NullString{})
	return seed
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

// countOne runs a COUNT query and returns its value, failing the test with
// label on error.
func (f *tenancyFixture) countOne(ctx context.Context, label, query string, args ...any) int {
	f.t.Helper()
	var n int
	if err := f.db.QueryRowContext(ctx, query, args...).Scan(&n); err != nil {
		f.t.Fatalf("%s: %v", label, err)
	}
	return n
}

// countTokensFor counts an organization's token rows, optionally of one type.
func (f *tenancyFixture) countTokensFor(ctx context.Context, orgID, tokenType string) int {
	return f.countOne(ctx, "count tokens", `
		SELECT COUNT(*) FROM ibex_core.tokens
		WHERE org_id = $1::uuid AND ($2 = '' OR type = $2)`, orgID, tokenType)
}

// countUsersFor counts an organization's user rows.
func (f *tenancyFixture) countUsersFor(ctx context.Context, orgID string) int {
	return f.countOne(ctx, "count users", `
		SELECT COUNT(*) FROM ibex_core.users WHERE org_id = $1::uuid`, orgID)
}

// queryID reads one text id, failing the test with label on error.
func (f *tenancyFixture) queryID(ctx context.Context, label, query string, args ...any) string {
	f.t.Helper()
	var id string
	if err := f.db.QueryRowContext(ctx, query, args...).Scan(&id); err != nil {
		f.t.Fatalf("%s: %v", label, err)
	}
	return id
}

// firstUserID returns the organization's first user id.
func (f *tenancyFixture) firstUserID(ctx context.Context, orgID string) string {
	return f.queryID(ctx, "read foreign user", `
		SELECT id::text FROM ibex_core.users WHERE org_id = $1::uuid`, orgID)
}

// firstAgentID returns the organization's first agent id.
func (f *tenancyFixture) firstAgentID(ctx context.Context, orgID string) string {
	return f.queryID(ctx, "read foreign agent", `
		SELECT id::text FROM ibex_core.agents WHERE org_id = $1::uuid`, orgID)
}

// createIdentity calls bootstrap_create_identity as the current role.
func createIdentity(ctx context.Context, tx *sql.Tx, call identityCall) error {
	// nosemgrep: go_sql_rule-concat-sqli -- static test fixture SQL; every value is a bound parameter.
	_, err := tx.ExecContext(ctx, `
		SELECT ibex_core.bootstrap_create_identity(
			$1::uuid, $2::uuid, $3, $4, $5::uuid, $6, $7)`,
		call.orgID, call.ids.user, call.slug+"@example.com", call.slug,
		call.ids.agent, call.slug+" agent", call.slug)
	return err
}

// insertPAT calls bootstrap_insert_pat as the current role.
func insertPAT(ctx context.Context, tx *sql.Tx, call patCall) error {
	// nosemgrep: go_sql_rule-concat-sqli -- static test fixture SQL; every value is a bound parameter.
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
	err := e.f.asBootstrap(e.t.Context(), func(tx *sql.Tx) error {
		return createIdentity(e.t.Context(), tx, call)
	})
	if err != nil {
		e.t.Fatalf("create identity for %s: %v", call.slug, err)
	}
}

// mustInsertPAT is the positive-control call for the bootstrap PAT.
func (e bootstrapEnv) mustInsertPAT(call patCall) {
	e.t.Helper()
	err := e.f.asBootstrap(e.t.Context(), func(tx *sql.Tx) error {
		return insertPAT(e.t.Context(), tx, call)
	})
	if err != nil {
		e.t.Fatalf("insert bootstrap PAT %s: %v", call.prefix, err)
	}
}

// requirePATRejected asserts bootstrap_insert_pat refuses call with SQLSTATE
// state and a message naming rule.
func (e bootstrapEnv) requirePATRejected(call patCall, state, rule string) {
	e.t.Helper()
	err := e.f.asBootstrap(e.t.Context(), func(tx *sql.Tx) error {
		return insertPAT(e.t.Context(), tx, call)
	})
	e.f.requireGuardError(err, sqlState{code: state}, rule)
}

// bootstrapIdentity creates an empty organization plus its identity through the
// definers, so every PAT subtest starts from a legal first install.
func (e bootstrapEnv) bootstrapIdentity(slug string) (string, identityIDs) {
	e.t.Helper()
	orgID := e.f.seedEmptyOrg(e.t.Context(), slug)
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
	err := e.f.asBootstrap(e.t.Context(), func(tx *sql.Tx) error {
		return upsertServiceTokenTx(e.t.Context(), tx, call, mask).Scan(&outcome, &tokenID)
	})
	return outcome, tokenID.String, err
}

// upsertServiceTokenTx runs the definer inside an existing transaction, so a
// test can observe the locks it holds before COMMIT.
func upsertServiceTokenTx(ctx context.Context, tx *sql.Tx, call serviceTokenCall, mask any) *sql.Row {
	// nosemgrep: go_sql_rule-concat-sqli -- static test fixture SQL; every value is a bound parameter.
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
	return e.f.asBootstrap(e.t.Context(), func(tx *sql.Tx) error {
		var outcome string
		var tokenID sql.NullString
		return upsertServiceTokenTx(e.t.Context(), tx, call, mask).Scan(&outcome, &tokenID)
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
	orgID := e.f.seedEmptyOrg(e.t.Context(), "first-install")
	ids := newIdentityIDs()
	e.mustCreateIdentity(identityCall{orgID: orgID, slug: "first-install", ids: ids})
	e.assertIdentityRows(orgID, ids)
}

// bootstrapIdentityRerunRefused proves a second identity cannot be added to an
// organization that already has one.
func bootstrapIdentityRerunRefused(e bootstrapEnv) {
	orgID := e.f.seedEmptyOrg(e.t.Context(), "re-run-target")
	ids := newIdentityIDs()
	e.mustCreateIdentity(identityCall{orgID: orgID, slug: "re-run-target", ids: ids})
	call := identityCall{orgID: orgID, slug: "re-run-again", ids: newIdentityIDs()}
	err := e.f.asBootstrap(e.t.Context(), func(tx *sql.Tx) error {
		return createIdentity(e.t.Context(), tx, call)
	})
	e.f.requireGuardError(err, sqlState{code: "42501"}, "already has a users row")
}

// bootstrapIdentityExistingOrgRefused proves the definer refuses a victim
// organization that already has a user and leaves its row untouched.
func bootstrapIdentityExistingOrgRefused(e bootstrapEnv) {
	victim := e.f.seedTenantNamed(e.t.Context(), "identity-victim")
	call := identityCall{orgID: victim.orgID, slug: "identity-attacker", ids: newIdentityIDs()}
	err := e.f.asBootstrap(e.t.Context(), func(tx *sql.Tx) error {
		return createIdentity(e.t.Context(), tx, call)
	})
	e.f.requireGuardError(err, sqlState{code: "42501"}, "already has a users row")
	if users := e.f.countUsersFor(e.t.Context(), victim.orgID); users != 1 {
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

// scanPair runs a two-column query, failing the test with label on error.
func (e bootstrapEnv) scanPair(label, query string, args ...any) (string, string) {
	e.t.Helper()
	var first, second string
	if err := e.f.db.QueryRowContext(e.t.Context(), query, args...).Scan(&first, &second); err != nil {
		e.t.Fatalf("%s: %v", label, err)
	}
	return first, second
}

// readOwnerUser returns the role and status of one user row.
func (e bootstrapEnv) readOwnerUser(orgID, userID string) (string, string) {
	return e.scanPair("read owner user", `
		SELECT role, status FROM ibex_core.users
		WHERE id = $1::uuid AND org_id = $2::uuid`, userID, orgID)
}

// readAgent returns the created_by and status of one agent row.
func (e bootstrapEnv) readAgent(orgID, agentID string) (string, string) {
	return e.scanPair("read agent", `
		SELECT created_by::text, status FROM ibex_core.agents
		WHERE id = $1::uuid AND org_id = $2::uuid`, agentID, orgID)
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
	orgID := e.f.seedEmptyOrg(e.t.Context(), "pat-org")
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
		e.requirePATRejected(call, "23514", "is not the bootstrap PAT grant")
	}
	if n := e.f.countTokensFor(e.t.Context(), orgID, ""); n != 0 {
		e.t.Fatalf("refused masks wrote %d tokens, want 0", n)
	}
}

// bootstrapPATSecondRefused proves an organization cannot own two PAT rows.
func bootstrapPATSecondRefused(e bootstrapEnv) {
	orgID, ids := e.bootstrapIdentity("pat-second")
	e.mustInsertPAT(patCall{orgID: orgID, ids: ids, prefix: "ibex_pat_one", mask: bootstrapMask})
	call := patCall{orgID: orgID, ids: ids, prefix: "ibex_pat_two", mask: bootstrapMask}
	e.requirePATRejected(call, "42501", "already owns a pat row")
}

// bootstrapPATForeignOwnerRefused proves the definer rejects a user that does
// not belong to the target organization.
func bootstrapPATForeignOwnerRefused(e bootstrapEnv) {
	owner, _ := e.bootstrapIdentity("pat-owner-org")
	target, targetIDs := e.bootstrapIdentity("pat-target-org")
	ids := identityIDs{user: e.f.firstUserID(e.t.Context(), owner), agent: targetIDs.agent}
	call := patCall{orgID: target, ids: ids, prefix: "ibex_pat_foreign", mask: bootstrapMask}
	e.requirePATRejected(call, "23514", "is not an active owner")
}

// bootstrapPATForeignAgentRefused proves the definer rejects an agent that does
// not belong to the target organization.
func bootstrapPATForeignAgentRefused(e bootstrapEnv) {
	owner, _ := e.bootstrapIdentity("pat-agent-org")
	target, targetIDs := e.bootstrapIdentity("pat-agent-target")
	ids := identityIDs{user: targetIDs.user, agent: e.f.firstAgentID(e.t.Context(), owner)}
	call := patCall{orgID: target, ids: ids, prefix: "ibex_pat_foreign_agent", mask: bootstrapMask}
	e.requirePATRejected(call, "23514", "is not an active agent")
}

// bootstrapPATBootstrappedOrgRefused proves an already bootstrapped victim
// organization keeps its original PAT and receives no attacker row.
func bootstrapPATBootstrappedOrgRefused(e bootstrapEnv) {
	victim := e.f.seedTenantNamed(e.t.Context(), "pat-victim")
	e.f.seedVictimPAT(e.t.Context(), victim)
	ids := identityIDs{user: victim.userID, agent: victim.agentID}
	call := patCall{orgID: victim.orgID, ids: ids, prefix: "ibex_pat_attacker", mask: bootstrapMask}
	err := e.f.asBootstrap(e.t.Context(), func(tx *sql.Tx) error {
		return insertPAT(e.t.Context(), tx, call)
	})
	e.f.requireGuardError(err, sqlState{code: "42501"}, "already owns a pat row")
	if n := e.f.countTokensFor(e.t.Context(), victim.orgID, "pat"); n != 1 {
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
	if err := e.f.db.QueryRowContext(e.t.Context(), `
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
	// nosemgrep: go_sql_rule-concat-sqli -- static test fixture SQL; every value is a bound parameter.
	if _, err := f.db.ExecContext(ctx, `
		INSERT INTO ibex_core.tokens (org_id, user_id, agent_id, type, hash, prefix, name, permissions)
		VALUES ($1::uuid, $2::uuid, $3::uuid, 'pat', $4, $5, 'victim bootstrap', $6)`,
		victim.orgID, victim.userID, victim.agentID, "hash-victim-"+victim.orgID,
		"ibex_pat_victim_"+victim.orgID[:8], bootstrapMask); err != nil {
		f.t.Fatalf("seed victim PAT: %v", err)
	}
}

// TestTenancyBootstrapModelPolicyGuard is the F1 lock for the model-policy
// definer. The allow-all fallback is a first-install write: a caller that names
// a tenant which already has a policy or an epoch must not be able to drop a
// wildcard allow row under a set an operator narrowed.
func TestTenancyBootstrapModelPolicyGuard(t *testing.T) {
	f := newTenancyFixture(t)
	runBootstrapCases(t, f, []bootstrapCase{
		{"first install writes the fallback", bootstrapModelPolicyFirstInstall},
		{"configured policy refused", bootstrapModelPolicyConfiguredRefused},
		{"existing epoch refused", bootstrapModelPolicyEpochRefused},
	})
}

// bootstrapModelPolicyFirstInstall proves the fallback and epoch a fresh
// organization receives.
func bootstrapModelPolicyFirstInstall(e bootstrapEnv) {
	orgID := e.f.seedEmptyOrg(e.t.Context(), "policy-first-install")
	if err := e.writeModelPolicy(orgID); err != nil {
		e.t.Fatalf("write model policy: %v", err)
	}
	e.assertModelPolicy(orgID, modelPolicyRow{allowed: true, priority: 1000, epoch: 1})
	if n := e.f.countModelPolicies(e.t.Context(), orgID); n != 1 {
		e.t.Fatalf("model policy rows = %d, want 1", n)
	}
}

// bootstrapModelPolicyConfiguredRefused proves a tenant with any policy row is
// refused and its row is untouched.
func bootstrapModelPolicyConfiguredRefused(e bootstrapEnv) {
	orgID := e.f.seedEmptyOrg(e.t.Context(), "policy-configured")
	seeded := modelPolicySeed{pattern: "gpt-*", allowed: false, priority: 10}
	e.f.seedModelPolicy(e.t.Context(), orgID, seeded)
	err := e.writeModelPolicy(orgID)
	e.f.requireGuardError(err, sqlState{code: "42501"}, "already has a model policy or epoch")
	if n := e.f.countModelPolicies(e.t.Context(), orgID); n != 1 {
		e.t.Fatalf("model policy rows = %d, want the seeded 1", n)
	}
	e.assertSeededPolicy(orgID, seeded)
}

// bootstrapModelPolicyEpochRefused proves an epoch alone (the partial state a
// previous write could leave) is enough to refuse, and writes no policy.
func bootstrapModelPolicyEpochRefused(e bootstrapEnv) {
	orgID := e.f.seedEmptyOrg(e.t.Context(), "policy-epoch")
	e.f.seedPolicyEpoch(e.t.Context(), orgID, 7)
	err := e.writeModelPolicy(orgID)
	e.f.requireGuardError(err, sqlState{code: "42501"}, "already has a model policy or epoch")
	if n := e.f.countModelPolicies(e.t.Context(), orgID); n != 0 {
		e.t.Fatalf("refused call wrote %d model policies, want 0", n)
	}
	if epoch := e.f.readPolicyEpoch(e.t.Context(), orgID); epoch != 7 {
		e.t.Fatalf("epoch = %d, want the seeded 7", epoch)
	}
}

// writeModelPolicy calls bootstrap_write_model_policy as ibex_bootstrap.
func (e bootstrapEnv) writeModelPolicy(orgID string) error {
	e.t.Helper()
	return e.f.asBootstrap(e.t.Context(), func(tx *sql.Tx) error {
		// nosemgrep: go_sql_rule-concat-sqli -- static test fixture SQL; orgID is a bound parameter.
		_, err := tx.ExecContext(e.t.Context(), `SELECT ibex_core.bootstrap_write_model_policy($1::uuid)`, orgID)
		return err
	})
}

// assertModelPolicy checks the wildcard fallback and its epoch.
func (e bootstrapEnv) assertModelPolicy(orgID string, want modelPolicyRow) {
	e.t.Helper()
	var got modelPolicyRow
	if err := e.f.db.QueryRowContext(e.t.Context(), `
		SELECT p.allowed, p.priority, m.epoch
		FROM ibex_core.org_model_policies p
		JOIN ibex_core.org_model_policy_meta m ON m.org_id = p.org_id
		WHERE p.org_id = $1::uuid AND p.model_pattern = '*'`, orgID).
		Scan(&got.allowed, &got.priority, &got.epoch); err != nil {
		e.t.Fatalf("read model policy: %v", err)
	}
	if got != want {
		e.t.Fatalf("model policy = %+v, want %+v", got, want)
	}
}

// assertSeededPolicy checks a seeded policy row is unchanged.
func (e bootstrapEnv) assertSeededPolicy(orgID string, want modelPolicySeed) {
	e.t.Helper()
	var gotAllowed bool
	var gotPriority int
	if err := e.f.db.QueryRowContext(e.t.Context(), `
		SELECT allowed, priority FROM ibex_core.org_model_policies
		WHERE org_id = $1::uuid AND model_pattern = $2`, orgID, want.pattern).
		Scan(&gotAllowed, &gotPriority); err != nil {
		e.t.Fatalf("read seeded policy %s: %v", want.pattern, err)
	}
	if gotAllowed != want.allowed || gotPriority != want.priority {
		e.t.Fatalf("seeded policy %s = allowed %v priority %d, want allowed %v priority %d",
			want.pattern, gotAllowed, gotPriority, want.allowed, want.priority)
	}
}

// seedModelPolicy inserts one policy row for orgID.
func (f *tenancyFixture) seedModelPolicy(ctx context.Context, orgID string, seed modelPolicySeed) {
	f.t.Helper()
	// nosemgrep: go_sql_rule-concat-sqli -- static test fixture SQL; every value is a bound parameter.
	if _, err := f.db.ExecContext(ctx, `
		INSERT INTO ibex_core.org_model_policies (org_id, model_pattern, allowed, priority)
		VALUES ($1::uuid, $2, $3, $4)`, orgID, seed.pattern, seed.allowed, seed.priority); err != nil {
		f.t.Fatalf("seed model policy %s: %v", seed.pattern, err)
	}
}

// seedPolicyEpoch inserts one epoch row for orgID.
func (f *tenancyFixture) seedPolicyEpoch(ctx context.Context, orgID string, epoch int) {
	f.t.Helper()
	if _, err := f.db.ExecContext(ctx, `
		INSERT INTO ibex_core.org_model_policy_meta (org_id, epoch) VALUES ($1::uuid, $2)`,
		orgID, epoch); err != nil {
		f.t.Fatalf("seed policy epoch: %v", err)
	}
}

// countModelPolicies counts orgID's policy rows.
func (f *tenancyFixture) countModelPolicies(ctx context.Context, orgID string) int {
	return f.countOne(ctx, "count model policies", `
		SELECT COUNT(*) FROM ibex_core.org_model_policies WHERE org_id = $1::uuid`, orgID)
}

// readPolicyEpoch returns orgID's epoch.
func (f *tenancyFixture) readPolicyEpoch(ctx context.Context, orgID string) int {
	f.t.Helper()
	var epoch int
	if err := f.db.QueryRowContext(ctx, `
		SELECT epoch FROM ibex_core.org_model_policy_meta WHERE org_id = $1::uuid`, orgID).Scan(&epoch); err != nil {
		f.t.Fatalf("read policy epoch: %v", err)
	}
	return epoch
}

// TestTenancyBootstrapServiceTokenGuard is the F1 lock for the service-token
// definer: an organization with no active owner or no active agent must be
// refused instead of receiving a credential with NULL subjects.
func TestTenancyBootstrapServiceTokenGuard(t *testing.T) {
	f := newTenancyFixture(t)
	runBootstrapCases(t, f, []bootstrapCase{
		{"organization without owner refused", bootstrapServiceTokenNoOwnerRefused},
		{"organization without agent refused", bootstrapServiceTokenNoAgentRefused},
		{"non-service mask refused", bootstrapServiceTokenMaskRefused},
		{"inserted then rotated", bootstrapServiceTokenRotates},
		{"rotation sweeps duplicate managed rows", bootstrapServiceTokenSweepsDuplicates},
		{"own prefix re-run is not a conflict", bootstrapServiceTokenOwnPrefixRerun},
		{"another organization's prefix refused", bootstrapServiceTokenForeignPrefixRefused},
	})
}

// bootstrapServiceTokenMaskRefused proves the rotation path rejects every mask
// but MemoryRead | MemoryWrite before it writes. A valid managed row exists
// first, so each rejected call reaches the guard against the UPDATE branch;
// without the guard that branch wrote p_permissions verbatim and a caller could
// rotate the organization's service credential into a full-admin grant. The
// row's hash, prefix and permissions must be byte-identical after every
// rejection.
func bootstrapServiceTokenMaskRefused(e bootstrapEnv) {
	tenant := e.bootstrapTenant("service-token-mask")
	valid := serviceTokenCall{orgID: tenant.orgID, hash: "hash-mask-valid", prefix: "ibex_pat_service_mask_valid"}
	tokenID := e.mustUpsertInserted(valid, "seed the managed service token")
	before := e.readServiceToken(tokenID)
	for i, mask := range []any{
		int64(permissions.ProxyChatCompletion),
		int64(permissions.Admin),
		int64(serviceTokenMask | permissions.MemoryDelete),
		nil,
	} {
		call := serviceTokenCall{
			orgID:  tenant.orgID,
			hash:   "hash-mask-" + strconv.Itoa(i),
			prefix: "ibex_pat_service_mask_" + strconv.Itoa(i),
		}
		e.f.requireGuardError(e.upsertServiceTokenRejected(call, mask), sqlState{code: "23514"}, "is not the memory-service grant")
		if after := e.readServiceToken(tokenID); after != before {
			e.t.Fatalf("rejected mask %v changed the token: before %+v, after %+v", mask, before, after)
		}
	}
	if n := e.f.countTokensFor(e.t.Context(), tenant.orgID, "service_token"); n != 1 {
		e.t.Fatalf("service token rows = %d, want the single seeded row", n)
	}
}

// bootstrapServiceTokenNoOwnerRefused proves an organization with an agent but
// no owner is refused and writes no token.
func bootstrapServiceTokenNoOwnerRefused(e bootstrapEnv) {
	e.assertServiceTokenSubjectMissing(e.f.seedAgentOnlyOrg(e.t.Context(), "token-no-owner"), "no active owner user")
}

// bootstrapServiceTokenNoAgentRefused proves an organization with an owner but
// no agent is refused and writes no token.
func bootstrapServiceTokenNoAgentRefused(e bootstrapEnv) {
	e.assertServiceTokenSubjectMissing(e.f.seedOwnerOnlyOrg(e.t.Context(), "token-no-agent"), "no active agent")
}

// assertServiceTokenSubjectMissing asserts the definer refuses the tenant on
// the named missing subject and writes no token, so each subject guard is
// proven on its own rather than both being absent at once.
func (e bootstrapEnv) assertServiceTokenSubjectMissing(tenant tenantSeed, rule string) {
	e.t.Helper()
	call := serviceTokenCall{
		orgID:  tenant.orgID,
		hash:   "hash-missing-subject",
		prefix: "ibex_pat_missing_" + tenant.orgID[:8],
	}
	outcome, tokenID, err := e.upsertServiceToken(call)
	if err == nil {
		e.t.Fatalf("expected a refusal, got outcome %q id %q", outcome, tokenID)
	}
	e.f.requireGuardError(err, sqlState{code: "23514"}, rule)
	if n := e.f.countTokensFor(e.t.Context(), tenant.orgID, ""); n != 0 {
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

// bootstrapServiceTokenSweepsDuplicates proves the rotation ends the call with
// exactly one active managed row: a row another writer left behind is revoked
// rather than left live beside the rotated credential. The definer picks the
// organization's oldest managed row, so the second row is the one the sweep
// must catch, and it must carry the reason the operator sees.
func bootstrapServiceTokenSweepsDuplicates(e bootstrapEnv) {
	tenant := e.bootstrapTenant("token-duplicates")
	older := e.f.seedManagedServiceToken(e.t.Context(), tenant, managedTokenSeed{
		hash: "hash-dup-older", prefix: "ibex_pat_dup_older", age: 3 * time.Minute,
	})
	first := serviceTokenCall{orgID: tenant.orgID, hash: "hash-dup-rotation", prefix: "ibex_pat_dup_rotation"}
	outcome, rotated, err := e.upsertServiceToken(first)
	if err != nil {
		e.t.Fatalf("rotate the seeded managed row: %v", err)
	}
	if outcome != "updated" || rotated != older {
		e.t.Fatalf("outcome %q for token %s, want updated on the seeded row %s", outcome, rotated, older)
	}

	duplicate := e.f.seedManagedServiceToken(e.t.Context(), tenant, managedTokenSeed{
		hash: "hash-dup-later", prefix: "ibex_pat_dup_later", age: time.Minute,
	})
	second := serviceTokenCall{orgID: tenant.orgID, hash: "hash-dup-final", prefix: "ibex_pat_dup_final"}
	outcome, rotatedAgain, err := e.upsertServiceToken(second)
	if err != nil {
		e.t.Fatalf("rotate with a duplicate present: %v", err)
	}
	if outcome != "updated" || rotatedAgain != older {
		e.t.Fatalf("outcome %q for token %s, want updated on %s", outcome, rotatedAgain, older)
	}
	e.assertSingleActiveManagedToken(tenant.orgID, older, duplicate)
}

// assertSingleActiveManagedToken asserts the organization holds one active
// memory-service row (wantActive), and that the only other managed row is the
// one the sweep revoked with the documented reason.
func (e bootstrapEnv) assertSingleActiveManagedToken(orgID, wantActive, wantRevoked string) {
	e.t.Helper()
	var active, swept int
	var activeID, revokedID string
	if err := e.f.db.QueryRowContext(e.t.Context(), `
		SELECT count(*) FILTER (WHERE NOT is_revoked),
		       count(*) FILTER (WHERE is_revoked
		                          AND revoke_reason = 'duplicate memory-service row'),
		       COALESCE(min(id::text) FILTER (WHERE NOT is_revoked), ''),
		       COALESCE(min(id::text) FILTER (WHERE is_revoked), '')
		FROM ibex_core.tokens
		WHERE org_id = $1::uuid
		  AND type = 'service_token'
		  AND name = 'memory-service'`, orgID).
		Scan(&active, &swept, &activeID, &revokedID); err != nil {
		e.t.Fatalf("read managed service rows: %v", err)
	}
	if active != 1 || activeID != wantActive {
		e.t.Fatalf("active managed rows = %d (id %s), want 1 (id %s)", active, activeID, wantActive)
	}
	if swept != 1 || revokedID != wantRevoked {
		e.t.Fatalf("swept managed rows = %d (id %s), want 1 (id %s)", swept, revokedID, wantRevoked)
	}
}

// seedManagedServiceToken inserts one managed memory-service row directly, as a
// writer that predates the definer could have left it, so the duplicate sweep
// has something to revoke.
func (f *tenancyFixture) seedManagedServiceToken(ctx context.Context, tenant tenantSeed, seed managedTokenSeed) string {
	f.t.Helper()
	var id string
	if err := f.db.QueryRowContext(ctx, `
		INSERT INTO ibex_core.tokens
			(org_id, user_id, agent_id, type, hash, prefix, name, permissions, created_at)
		VALUES ($1::uuid, $2::uuid, $3::uuid, 'service_token', $4, $5, 'memory-service',
		        $6, $7)
		RETURNING id::text`,
		tenant.orgID, tenant.userID, tenant.agentID, seed.hash, seed.prefix,
		serviceTokenMask, time.Now().Add(-seed.age)).Scan(&id); err != nil {
		f.t.Fatalf("seed managed service token %s: %v", seed.prefix, err)
	}
	return id
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
	holder := e.f.seedTenantNamed(e.t.Context(), "prefix-holder")
	e.f.seedTokenFor(e.t.Context(), holder.orgID, tokenSeed{prefix: "ibex_pat_held", hash: "hash-held"})
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
	if n := e.f.countTokensFor(e.t.Context(), tenant.orgID, ""); n != 0 {
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
	before := e.f.serviceTokenID(e.t.Context(), tenant.orgID)
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

// upsertServiceTokenChecked calls the definer and fails the test with label on
// error, returning the outcome and the token id.
func (e bootstrapEnv) upsertServiceTokenChecked(call serviceTokenCall, label string) (string, string) {
	e.t.Helper()
	outcome, tokenID, err := e.upsertServiceToken(call)
	if err != nil {
		e.t.Fatalf("%s: %v", label, err)
	}
	return outcome, tokenID
}

// assertServiceTokenReplay covers the same-prefix re-run: it updates the same
// row instead of reporting a conflict with the caller's own organization.
func (e bootstrapEnv) assertServiceTokenReplay(call serviceTokenCall, label, wantID string) {
	e.t.Helper()
	outcome, tokenID := e.upsertServiceTokenChecked(call, label)
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
	outcome, tokenID := e.upsertServiceTokenChecked(call, label)
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

// readServiceToken returns one token row's subject binding, prefix, hash and
// permissions, so a rejected rotation can be compared field by field.
func (e bootstrapEnv) readServiceToken(tokenID string) serviceTokenRow {
	e.t.Helper()
	var row serviceTokenRow
	if err := e.f.db.QueryRowContext(e.t.Context(), `
		SELECT user_id::text, agent_id::text, prefix, hash, permissions
		FROM ibex_core.tokens WHERE id = $1::uuid`, tokenID).
		Scan(&row.userID, &row.agentID, &row.prefix, &row.hash, &row.permissions); err != nil {
		e.t.Fatalf("read service token: %v", err)
	}
	return row
}

// serviceTokenID returns the organization's managed memory-service token id.
func (f *tenancyFixture) serviceTokenID(ctx context.Context, orgID string) string {
	return f.queryID(ctx, "read service token id", `
		SELECT id::text FROM ibex_core.tokens
		WHERE org_id = $1::uuid AND type = 'service_token' AND name = 'memory-service'`,
		orgID)
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
