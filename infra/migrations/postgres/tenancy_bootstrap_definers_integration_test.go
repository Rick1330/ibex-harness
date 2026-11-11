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

// createIdentity calls bootstrap_create_identity as the current role.
func createIdentity(ctx context.Context, tx *sql.Tx, orgID, slug string, ids identityIDs) error {
	_, err := tx.ExecContext(ctx, `
		SELECT ibex_core.bootstrap_create_identity(
			$1::uuid, $2::uuid, $3, $4, $5::uuid, $6, $7)`,
		orgID, ids.user, slug+"@example.com", slug, ids.agent, slug+" agent", slug)
	return err
}

// TestTenancyBootstrapCreateIdentityGuard is the F1 lock for the identity
// definer. The attack it closes is a bootstrap caller naming an organization it
// does not own and adding an owner user to it.
func TestTenancyBootstrapCreateIdentityGuard(t *testing.T) {
	f := newTenancyFixture(t)
	ctx := t.Context()

	t.Run("first install succeeds", func(t *testing.T) {
		f := f.sub(t)
		orgID := f.seedEmptyOrg(ctx, "first-install")
		ids := newIdentityIDs()
		err := f.asBootstrap(ctx, func(tx *sql.Tx) error {
			return createIdentity(ctx, tx, orgID, "first-install", ids)
		})
		if err != nil {
			t.Fatalf("first install: %v", err)
		}
		assertIdentityRows(t, f, ctx, orgID, ids)
	})

	t.Run("re-run refused", func(t *testing.T) {
		f := f.sub(t)
		orgID := f.seedEmptyOrg(ctx, "re-run-target")
		ids := newIdentityIDs()
		mustCreateIdentity(t, f, ctx, orgID, "re-run-target", ids)
		err := f.asBootstrap(ctx, func(tx *sql.Tx) error {
			return createIdentity(ctx, tx, orgID, "re-run-again", newIdentityIDs())
		})
		f.requireGuardError(err, sqlState{code: "42501"}, "already has a users row")
	})

	t.Run("existing organization refused", func(t *testing.T) {
		f := f.sub(t)
		victim := f.seedTenantNamed(ctx, "identity-victim")
		err := f.asBootstrap(ctx, func(tx *sql.Tx) error {
			return createIdentity(ctx, tx, victim.orgID, "identity-attacker", newIdentityIDs())
		})
		f.requireGuardError(err, sqlState{code: "42501"}, "already has a users row")
		var users int
		if err := f.db.QueryRowContext(ctx,
			`SELECT COUNT(*) FROM ibex_core.users WHERE org_id = $1::uuid`, victim.orgID).Scan(&users); err != nil {
			t.Fatalf("count victim users: %v", err)
		}
		if users != 1 {
			t.Fatalf("victim organization has %d users, want its original 1", users)
		}
	})
}

// mustCreateIdentity is the positive-control call for a fresh organization.
func mustCreateIdentity(t *testing.T, f *tenancyFixture, ctx context.Context, orgID, slug string, ids identityIDs) {
	t.Helper()
	err := f.asBootstrap(ctx, func(tx *sql.Tx) error {
		return createIdentity(ctx, tx, orgID, slug, ids)
	})
	if err != nil {
		t.Fatalf("create identity for %s: %v", slug, err)
	}
}

// assertIdentityRows checks the owner user and the agent the definer wrote.
func assertIdentityRows(t *testing.T, f *tenancyFixture, ctx context.Context, orgID string, ids identityIDs) {
	t.Helper()
	var role, status string
	if err := f.db.QueryRowContext(ctx, `
		SELECT role, status FROM ibex_core.users
		WHERE id = $1::uuid AND org_id = $2::uuid`, ids.user, orgID).Scan(&role, &status); err != nil {
		t.Fatalf("read owner user: %v", err)
	}
	if role != "owner" || status != "active" {
		t.Fatalf("owner user role/status = %s/%s, want owner/active", role, status)
	}
	var createdBy, agentStatus string
	if err := f.db.QueryRowContext(ctx, `
		SELECT created_by::text, status FROM ibex_core.agents
		WHERE id = $1::uuid AND org_id = $2::uuid`, ids.agent, orgID).Scan(&createdBy, &agentStatus); err != nil {
		t.Fatalf("read agent: %v", err)
	}
	if createdBy != ids.user || agentStatus != "active" {
		t.Fatalf("agent created_by/status = %s/%s, want %s/active", createdBy, agentStatus, ids.user)
	}
}

// insertPAT calls bootstrap_insert_pat as the current role.
func insertPAT(ctx context.Context, tx *sql.Tx, orgID string, ids identityIDs, prefix string, mask int64) error {
	_, err := tx.ExecContext(ctx, `
		SELECT ibex_core.bootstrap_insert_pat(
			$1::uuid, $2::uuid, $3::uuid, $4::uuid, $5, $6, $7, $8::bigint)`,
		uuid.NewString(), orgID, ids.user, ids.agent, "hash-"+prefix, prefix, "bootstrap", mask)
	return err
}

// TestTenancyBootstrapPATGuard is the F1 lock for the PAT definer.
func TestTenancyBootstrapPATGuard(t *testing.T) {
	f := newTenancyFixture(t)
	ctx := t.Context()

	t.Run("bootstrap PAT accepted", func(t *testing.T) {
		f := f.sub(t)
		orgID := f.seedEmptyOrg(ctx, "pat-org")
		ids := newIdentityIDs()
		mustCreateIdentity(t, f, ctx, orgID, "pat-org", ids)
		mustInsertPAT(t, f, ctx, orgID, ids, "ibex_pat_first", bootstrapMask)
		assertBootstrapPAT(t, f, ctx, orgID, "ibex_pat_first")
	})

	t.Run("non-bootstrap mask refused", func(t *testing.T) {
		f := f.sub(t)
		orgID, ids := f.bootstrapIdentity(ctx, "pat-mask")
		for _, mask := range []int64{
			permissions.Admin | permissions.SecretUse,
			bootstrapMask | permissions.OperatorRawRead,
			1099511627775,
		} {
			err := f.asBootstrap(ctx, func(tx *sql.Tx) error {
				return insertPAT(ctx, tx, orgID, ids, "ibex_pat_mask", mask)
			})
			f.requireGuardError(err, sqlState{code: "23514"}, "is not the bootstrap PAT grant")
		}
		if n := f.countTokensFor(ctx, orgID, ""); n != 0 {
			t.Fatalf("refused masks wrote %d tokens, want 0", n)
		}
	})

	t.Run("second PAT refused", func(t *testing.T) {
		f := f.sub(t)
		orgID, ids := f.bootstrapIdentity(ctx, "pat-second")
		mustInsertPAT(t, f, ctx, orgID, ids, "ibex_pat_one", bootstrapMask)
		err := f.asBootstrap(ctx, func(tx *sql.Tx) error {
			return insertPAT(ctx, tx, orgID, ids, "ibex_pat_two", bootstrapMask)
		})
		f.requireGuardError(err, sqlState{code: "42501"}, "already owns a pat row")
	})

	t.Run("foreign owner refused", func(t *testing.T) {
		f := f.sub(t)
		owner, _ := f.bootstrapIdentity(ctx, "pat-owner-org")
		target, targetIDs := f.bootstrapIdentity(ctx, "pat-target-org")
		var foreignUser string
		if err := f.db.QueryRowContext(ctx, `
			SELECT id::text FROM ibex_core.users WHERE org_id = $1::uuid`, owner).Scan(&foreignUser); err != nil {
			t.Fatalf("read foreign user: %v", err)
		}
		ids := identityIDs{user: foreignUser, agent: targetIDs.agent}
		err := f.asBootstrap(ctx, func(tx *sql.Tx) error {
			return insertPAT(ctx, tx, target, ids, "ibex_pat_foreign", bootstrapMask)
		})
		f.requireGuardError(err, sqlState{code: "23514"}, "is not an active owner")
	})

	t.Run("foreign agent refused", func(t *testing.T) {
		f := f.sub(t)
		owner, _ := f.bootstrapIdentity(ctx, "pat-agent-org")
		target, targetIDs := f.bootstrapIdentity(ctx, "pat-agent-target")
		var foreignAgent string
		if err := f.db.QueryRowContext(ctx, `
			SELECT id::text FROM ibex_core.agents WHERE org_id = $1::uuid`, owner).Scan(&foreignAgent); err != nil {
			t.Fatalf("read foreign agent: %v", err)
		}
		ids := identityIDs{user: targetIDs.user, agent: foreignAgent}
		err := f.asBootstrap(ctx, func(tx *sql.Tx) error {
			return insertPAT(ctx, tx, target, ids, "ibex_pat_foreign_agent", bootstrapMask)
		})
		f.requireGuardError(err, sqlState{code: "23514"}, "is not an active agent")
	})

	t.Run("bootstrapped organization refused", func(t *testing.T) {
		f := f.sub(t)
		victim := f.seedTenantNamed(ctx, "pat-victim")
		f.seedVictimPAT(ctx, victim)
		ids := identityIDs{user: victim.userID, agent: victim.agentID}
		err := f.asBootstrap(ctx, func(tx *sql.Tx) error {
			return insertPAT(ctx, tx, victim.orgID, ids, "ibex_pat_attacker", bootstrapMask)
		})
		f.requireGuardError(err, sqlState{code: "42501"}, "already owns a pat row")
		if n := f.countTokensFor(ctx, victim.orgID, "pat"); n != 1 {
			t.Fatalf("victim organization has %d pat rows, want its original 1", n)
		}
	})
}

// bootstrapIdentity creates an empty organization plus its identity through the
// definers, so every PAT subtest starts from a legal first install.
func (f *tenancyFixture) bootstrapIdentity(ctx context.Context, slug string) (string, identityIDs) {
	f.t.Helper()
	orgID := f.seedEmptyOrg(ctx, slug)
	ids := newIdentityIDs()
	mustCreateIdentity(f.t, f, ctx, orgID, slug, ids)
	return orgID, ids
}

// mustInsertPAT is the positive-control call for the bootstrap PAT.
func mustInsertPAT(t *testing.T, f *tenancyFixture, ctx context.Context, orgID string, ids identityIDs, prefix string, mask int64) {
	t.Helper()
	err := f.asBootstrap(ctx, func(tx *sql.Tx) error {
		return insertPAT(ctx, tx, orgID, ids, prefix, mask)
	})
	if err != nil {
		t.Fatalf("insert bootstrap PAT %s: %v", prefix, err)
	}
}

// assertBootstrapPAT checks the row the definer wrote.
func assertBootstrapPAT(t *testing.T, f *tenancyFixture, ctx context.Context, orgID, prefix string) {
	t.Helper()
	var tokenType string
	var mask int64
	var revoked bool
	var expiresAt sql.NullTime
	if err := f.db.QueryRowContext(ctx, `
		SELECT type, permissions, is_revoked, expires_at FROM ibex_core.tokens
		WHERE org_id = $1::uuid AND prefix = $2`, orgID, prefix).
		Scan(&tokenType, &mask, &revoked, &expiresAt); err != nil {
		t.Fatalf("read bootstrap PAT: %v", err)
	}
	if tokenType != "pat" {
		t.Fatalf("type = %s, want pat", tokenType)
	}
	if mask != bootstrapMask {
		t.Fatalf("permissions = %d, want the bootstrap mask %d", mask, bootstrapMask)
	}
	if revoked || expiresAt.Valid {
		t.Fatalf("bootstrap PAT revoked=%v expires_at=%v, want neither", revoked, expiresAt)
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

// upsertServiceToken calls bootstrap_upsert_service_token as ibex_bootstrap and
// returns its named outcome plus the token id (empty when the outcome carries
// none).
func (f *tenancyFixture) upsertServiceToken(ctx context.Context, orgID, hash, prefix string) (string, string, error) {
	f.t.Helper()
	var outcome string
	var tokenID sql.NullString
	err := f.asBootstrap(ctx, func(tx *sql.Tx) error {
		return tx.QueryRowContext(ctx, `
			SELECT outcome, token_id::text
			FROM ibex_core.bootstrap_upsert_service_token($1::uuid, $2, $3, $4::bigint)`,
			orgID, hash, prefix, int64(permissions.ProxyChatCompletion)).
			Scan(&outcome, &tokenID)
	})
	return outcome, tokenID.String, err
}

// TestTenancyBootstrapServiceTokenGuard is the F1 lock for the service-token
// definer: an organization with no active owner or no active agent must be
// refused instead of receiving a credential with NULL subjects.
func TestTenancyBootstrapServiceTokenGuard(t *testing.T) {
	f := newTenancyFixture(t)
	ctx := t.Context()

	t.Run("organization without subjects refused", func(t *testing.T) {
		f := f.sub(t)
		orgID := f.seedEmptyOrg(ctx, "token-no-subjects")
		outcome, tokenID, err := f.upsertServiceToken(ctx, orgID, "hash-no-subjects", "ibex_pat_no_subjects")
		if err == nil {
			t.Fatalf("expected a refusal, got outcome %q id %q", outcome, tokenID)
		}
		f.requireGuardError(err, sqlState{code: "23514"}, "no active owner user")
		if n := f.countTokensFor(ctx, orgID, ""); n != 0 {
			t.Fatalf("refused upsert wrote %d tokens, want 0", n)
		}
	})

	t.Run("inserted then rotated", func(t *testing.T) {
		f := f.sub(t)
		tenant := f.bootstrapTenant(ctx, "token-rotates")
		assertServiceTokenInserted(t, f, ctx, tenant)
		assertServiceTokenRotated(t, f, ctx, tenant)
	})

	t.Run("own prefix re-run is not a conflict", func(t *testing.T) {
		f := f.sub(t)
		tenant := f.bootstrapTenant(ctx, "token-rerun")
		outcome, tokenID, err := f.upsertServiceToken(ctx, tenant.orgID, "hash-rerun", "ibex_pat_rerun")
		if err != nil || outcome != "inserted" {
			t.Fatalf("first call: outcome %q err %v, want inserted", outcome, err)
		}
		// The same operator re-run: the prefix already belongs to this
		// organization, on this row, so the prefix check must exclude the
		// caller's own org instead of reporting a conflict with itself.
		outcome, tokenID2, err := f.upsertServiceToken(ctx, tenant.orgID, "hash-rerun", "ibex_pat_rerun")
		if err != nil || outcome != "updated" || tokenID2 != tokenID {
			t.Fatalf("re-run: outcome %q id %q err %v, want updated on %s", outcome, tokenID2, err, tokenID)
		}
	})

	t.Run("another organization's prefix refused", func(t *testing.T) {
		f := f.sub(t)
		holder := f.seedTenantNamed(ctx, "prefix-holder")
		f.seedTokenFor(ctx, holder.orgID, tokenSeed{prefix: "ibex_pat_held", hash: "hash-held"})
		tenant := f.bootstrapTenant(ctx, "prefix-taker")
		outcome, tokenID, err := f.upsertServiceToken(ctx, tenant.orgID, "hash-taker", "ibex_pat_held")
		if err != nil {
			t.Fatalf("prefix conflict: %v", err)
		}
		if outcome != "prefix_conflict" || tokenID != "" {
			t.Fatalf("outcome = %q id = %q, want prefix_conflict with no id", outcome, tokenID)
		}
		if n := f.countTokensFor(ctx, tenant.orgID, ""); n != 0 {
			t.Fatalf("conflicting org wrote %d tokens, want 0", n)
		}
	})
}

// bootstrapTenant creates an organization plus the owner user and agent the
// service-token definer requires, through the definers themselves.
func (f *tenancyFixture) bootstrapTenant(ctx context.Context, slug string) tenantSeed {
	f.t.Helper()
	orgID, ids := f.bootstrapIdentity(ctx, slug)
	return tenantSeed{orgID: orgID, userID: ids.user, agentID: ids.agent}
}

// assertServiceTokenInserted covers the first call and its subject binding.
func assertServiceTokenInserted(t *testing.T, f *tenancyFixture, ctx context.Context, tenant tenantSeed) {
	t.Helper()
	outcome, tokenID, err := f.upsertServiceToken(ctx, tenant.orgID, "hash-first", "ibex_pat_service_first")
	if err != nil {
		t.Fatalf("insert service token: %v", err)
	}
	if outcome != "inserted" || tokenID == "" {
		t.Fatalf("outcome = %q id = %q, want inserted with an id", outcome, tokenID)
	}
	assertServiceTokenSubjects(t, f, ctx, tokenID, tenant, "ibex_pat_service_first")
}

// assertServiceTokenRotated covers the re-run: same row, new hash and prefix,
// subjects still bound.
func assertServiceTokenRotated(t *testing.T, f *tenancyFixture, ctx context.Context, tenant tenantSeed) {
	t.Helper()
	before := f.serviceTokenID(ctx, tenant.orgID)
	outcome, tokenID, err := f.upsertServiceToken(ctx, tenant.orgID, "hash-second", "ibex_pat_service_second")
	if err != nil {
		t.Fatalf("rotate service token: %v", err)
	}
	if outcome != "updated" || tokenID != before {
		t.Fatalf("outcome = %q id = %q, want updated on %s", outcome, tokenID, before)
	}
	assertServiceTokenSubjects(t, f, ctx, before, tenant, "ibex_pat_service_second")
}

// assertServiceTokenSubjects checks the row is bound, not NULL, and carries the
// prefix the rotation wrote.
func assertServiceTokenSubjects(t *testing.T, f *tenancyFixture, ctx context.Context, tokenID string, tenant tenantSeed, prefix string) {
	t.Helper()
	var userID, agentID, gotPrefix string
	if err := f.db.QueryRowContext(ctx, `
		SELECT user_id::text, agent_id::text, prefix FROM ibex_core.tokens
		WHERE id = $1::uuid`, tokenID).Scan(&userID, &agentID, &gotPrefix); err != nil {
		t.Fatalf("read service token: %v", err)
	}
	if userID != tenant.userID || agentID != tenant.agentID {
		t.Fatalf("service token subjects = %s/%s, want %s/%s", userID, agentID, tenant.userID, tenant.agentID)
	}
	if gotPrefix != prefix {
		t.Fatalf("prefix = %s, want %s", gotPrefix, prefix)
	}
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
