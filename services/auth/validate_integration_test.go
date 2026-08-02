//go:build integration

package auth_test

import (
	"context"
	"database/sql"
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/infra/testing/testutil"
	"github.com/Rick1330/ibex-harness/services/auth/internal/repository"
	"github.com/Rick1330/ibex-harness/services/auth/internal/token"
	"github.com/google/uuid"
	"google.golang.org/protobuf/types/known/timestamppb"
)

type validateEnv struct {
	v      *token.Validator
	repo   *repository.TokensRepository
	argon2 token.Argon2Params
}

type orgRef struct {
	id string
}

type optionalScope struct {
	orgID   string
	userID  string
	agentID string
}

type bearerRef struct {
	raw string
}

func TestValidateTokenIntegration(t *testing.T) {
	dsn, cleanup := testutil.SetupPostgres(t)
	defer cleanup()

	db := testutil.OpenDB(t, dsn)
	defer db.Close()

	env := newValidateEnv(t, db)
	orgA := orgRef{id: testutil.SeedOrganization(t, db, "Org A", "org-a-val-"+uuid.NewString()[:8])}
	orgB := orgRef{id: testutil.SeedOrganization(t, db, "Org B", "org-b-val-"+uuid.NewString()[:8])}

	env.assertValidateOK(t, orgA, 42)
	env.assertUnauthenticated(t, bearerRef{raw: "ibex_pat_" + uuid.NewString() + "_wrong"})
	env.assertRevokedRejected(t, orgA)
	env.assertValidateOrg(t, orgB, 99)
	env.assertOversizedRejected(t)
}

func (e validateEnv) assertOversizedRejected(t *testing.T) {
	t.Helper()
	secret := strings.Repeat("x", 200)
	e.assertUnauthenticated(t, bearerRef{raw: "ibex_pat_" + uuid.NewString() + "_" + secret})
}

func TestValidateTokenOptionalFields(t *testing.T) {
	dsn, cleanup := testutil.SetupPostgres(t)
	defer cleanup()

	db := testutil.OpenDB(t, dsn)
	defer db.Close()

	env := newValidateEnv(t, db)
	orgID := testutil.SeedOrganization(t, db, "Optional Fields Org", "opt-"+uuid.NewString()[:8])
	userID := testutil.SeedUser(t, db, orgID, "opt-"+uuid.NewString()[:8]+"@test.local", "Opt User")
	agentID := testutil.SeedAgent(t, db, orgID, userID, "Opt Agent", "opt-agent-"+uuid.NewString()[:8])
	env.assertOptionalFields(t, optionalScope{orgID: orgID, userID: userID, agentID: agentID})
}

func newValidateEnv(t *testing.T, db *sql.DB) validateEnv {
	t.Helper()
	repo := repository.RequireTokensRepository(t, db, nil)
	lookup, err := token.NewRepoLookup(repo)
	if err != nil {
		t.Fatalf("NewRepoLookup: %v", err)
	}
	argon2 := token.TestArgon2Params()
	v, err := token.NewValidator(lookup, argon2)
	if err != nil {
		t.Fatalf("NewValidator: %v", err)
	}
	return validateEnv{
		v: v, repo: repo, argon2: argon2,
	}
}

func (e validateEnv) mustHash(t *testing.T, bearer bearerRef) string {
	t.Helper()
	hash, err := token.HashForTest(bearer.raw, e.argon2)
	if err != nil {
		t.Fatalf("hash: %v", err)
	}
	return hash
}

func (e validateEnv) insertActivePAT(t *testing.T, org orgRef, perms int64) bearerRef {
	t.Helper()
	tokenID := uuid.New()
	bearer := bearerRef{raw: "ibex_pat_" + tokenID.String() + "_integrationsecret"}
	prefix := "ibex_pat_" + tokenID.String()
	hash := e.mustHash(t, bearer)
	_, err := e.repo.InsertTestToken(context.Background(), org.id, prefix, hash, "test-pat", perms, false, nil)
	if err != nil {
		t.Fatalf("insert token: %v", err)
	}
	return bearer
}

func (e validateEnv) assertValidateOK(t *testing.T, org orgRef, perms int64) {
	t.Helper()
	bearer := e.insertActivePAT(t, org, perms)
	resp, err := e.v.Validate(context.Background(), bearer.raw)
	if err != nil {
		t.Fatalf("validate: %v", err)
	}
	if resp.GetOrgId() != org.id {
		t.Fatalf("org=%s want %s", resp.GetOrgId(), org.id)
	}
	if resp.GetPermissions() != perms {
		t.Fatalf("perms=%d want %d", resp.GetPermissions(), perms)
	}
}

func (e validateEnv) assertUnauthenticated(t *testing.T, bearer bearerRef) {
	t.Helper()
	_, err := e.v.Validate(context.Background(), bearer.raw)
	if !errors.Is(err, token.ErrUnauthenticated) {
		t.Fatalf("expected unauthenticated, got %v", err)
	}
}

func (e validateEnv) assertRevokedRejected(t *testing.T, org orgRef) {
	t.Helper()
	revokedID := uuid.New()
	revokedBearer := bearerRef{raw: "ibex_pat_" + revokedID.String() + "_revoked"}
	revokedHash := e.mustHash(t, revokedBearer)
	_, err := e.repo.InsertTestToken(context.Background(), org.id, "ibex_pat_"+revokedID.String(), revokedHash, "revoked", 1, true, nil)
	if err != nil {
		t.Fatalf("insert revoked: %v", err)
	}
	e.assertUnauthenticated(t, revokedBearer)
}

func (e validateEnv) assertValidateOrg(t *testing.T, org orgRef, perms int64) {
	t.Helper()
	bearer := e.insertActivePAT(t, org, perms)
	resp, err := e.v.Validate(context.Background(), bearer.raw)
	if err != nil {
		t.Fatalf("validate org: %v", err)
	}
	if resp.GetOrgId() != org.id {
		t.Fatalf("org id: got %s want %s", resp.GetOrgId(), org.id)
	}
}

func (e validateEnv) assertOptionalFields(t *testing.T, scope optionalScope) {
	t.Helper()
	tokenID := uuid.New()
	bearer := bearerRef{raw: "ibex_pat_" + tokenID.String() + "_optionalfields"}
	prefix := "ibex_pat_" + tokenID.String()
	hash := e.mustHash(t, bearer)
	expires := token.FutureExpiry()
	_, err := e.repo.CreateToken(context.Background(), repository.CreateTokenParams{
		ID: tokenID.String(), OrgID: scope.orgID, Name: "scoped-pat",
		Hash: hash, Prefix: prefix, Permissions: 55,
		UserID: &scope.userID, AgentID: &scope.agentID, ExpiresAt: expires,
	})
	if err != nil {
		t.Fatalf("insert scoped token: %v", err)
	}
	resp, err := e.v.Validate(context.Background(), bearer.raw)
	if err != nil {
		t.Fatalf("validate: %v", err)
	}
	if resp.GetUserId() != scope.userID {
		t.Fatalf("user_id: got %q want %q", resp.GetUserId(), scope.userID)
	}
	if resp.GetAgentId() != scope.agentID {
		t.Fatalf("agent_id: got %q want %q", resp.GetAgentId(), scope.agentID)
	}
	assertExpiresMatches(t, resp.GetExpiresAt(), expires)
}

func assertExpiresMatches(t *testing.T, got *timestamppb.Timestamp, want *time.Time) {
	t.Helper()
	if got == nil {
		t.Fatal("expected expires_at in response")
	}
	if want == nil {
		t.Fatal("want expires nil")
	}
	gotT := got.AsTime().UTC().Truncate(time.Second)
	wantT := want.UTC().Truncate(time.Second)
	if gotT != wantT {
		t.Fatalf("expires_at mismatch: got %v want %v", gotT, wantT)
	}
}
