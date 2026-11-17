//go:build integration

package bootstrap

import (
	"context"
	"database/sql"
	"net/url"
	"os"
	"strings"
	"testing"

	"github.com/Rick1330/ibex-harness/infra/testing/testutil"
	"github.com/Rick1330/ibex-harness/packages/crypto"
	"github.com/Rick1330/ibex-harness/packages/permissions"
	"github.com/Rick1330/ibex-harness/services/auth/internal/token"
	"github.com/google/uuid"
)

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

// reconcileRefusalSeed is one already-bootstrapped tenant whose memory-token
// reconciliation must fail closed. Each case seeds exactly one refusal
// condition and names the message that condition owes the operator.
type reconcileRefusalSeed struct {
	condition string // the seeded condition, named in every failure message
	update    string // service-account UPDATE that seeds it; $1 is the org id
	want      string // substring the refusal must carry
	rotate    bool   // replace the memory token before the rerun
}

// assertReconcileRefusal boots one tenant, seeds the case's refusal condition,
// and proves the rerun refuses with the message that condition owes.
func assertReconcileRefusal(t *testing.T, seed reconcileRefusalSeed) {
	t.Helper()
	f := newBootstrapFixture(t)
	first := f.run()

	f.execServiceTx(func(ctx context.Context, tx *sql.Tx) {
		if _, err := tx.ExecContext(ctx, seed.update, first.OrgID.String()); err != nil {
			t.Fatalf("seed refusal condition %q: %v", seed.condition, err)
		}
	})

	// A rotated bearer means only a fresh write could pass; the first run's
	// bound row must not be able to absorb the rerun.
	if seed.rotate {
		f.cfg.MemoryToken = generatePAT(t)
	}

	_, err := bootstrap(context.Background(), f.db, f.cfg)
	if err == nil || !strings.Contains(err.Error(), seed.want) {
		t.Fatalf("bootstrap with %s error = %v, want a refusal naming %q", seed.condition, err, seed.want)
	}
}

// TestBootstrapIntegrationRejectsMissingActiveAgent proves reconciliation fails
// closed instead of writing a token that no agent scopes.
func TestBootstrapIntegrationRejectsMissingActiveAgent(t *testing.T) {
	assertReconcileRefusal(t, reconcileRefusalSeed{
		condition: "no active agent",
		update:    `UPDATE ibex_core.agents SET status = 'archived' WHERE org_id = $1`,
		want:      "no active agent",
		rotate:    true,
	})
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
	assertReconcileRefusal(t, reconcileRefusalSeed{
		condition: "a soft-deleted slug",
		update:    `UPDATE ibex_core.organizations SET deleted_at = NOW() WHERE id = $1`,
		want:      "soft-deleted",
	})
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
	ownerDB, dsn := openIntegrationDB(t)

	cfg := newBootstrapConfig(t, openCapabilityDSN(t, dsn, "ibex_bootstrap", testutil.BootstrapLoginTestPassword),
		uuid.NewString(), "login-owner@example.com")
	cfg.OrgName = "Bootstrap As Login"
	cfg.MemoryToken = generatePAT(t)
	// Shared test database: this run is a deliberate second tenant.
	cfg.AllowSecondOrg = true
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
