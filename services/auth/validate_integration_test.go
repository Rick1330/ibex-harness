//go:build integration

package auth_test

import (
	"context"
	"database/sql"
	"errors"
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

func TestValidateTokenIntegration(t *testing.T) {
	dsn, cleanup := testutil.SetupPostgres(t)
	defer cleanup()

	db := testutil.OpenDB(t, dsn)
	defer db.Close()

	env := newValidateEnv(t, db)
	orgA := testutil.SeedOrganization(t, db, "Org A", "org-a-val-"+uuid.NewString()[:8])
	orgB := testutil.SeedOrganization(t, db, "Org B", "org-b-val-"+uuid.NewString()[:8])

	env.assertValidateOK(t, orgA, 42)
	env.assertUnauthenticated(t, "ibex_pat_"+uuid.NewString()+"_wrong")
	env.assertRevokedRejected(t, orgA)
	env.assertValidateOrg(t, orgB, 99)
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
	env.assertOptionalFields(t, orgID, userID, agentID)
}

func newValidateEnv(t *testing.T, db *sql.DB) validateEnv {
	t.Helper()
	repo := repository.NewTokensRepository(db, nil)
	lookup, err := token.NewRepoLookup(repo)
	if err != nil {
		t.Fatalf("NewRepoLookup: %v", err)
	}
	argon2 := token.DefaultArgon2Params()
	return validateEnv{
		v: token.NewValidator(lookup, argon2), repo: repo, argon2: argon2,
	}
}

func (e validateEnv) mustHash(t *testing.T, bearer string) string {
	t.Helper()
	hash, err := token.HashForTest(bearer, e.argon2)
	if err != nil {
		t.Fatalf("hash: %v", err)
	}
	return hash
}

func (e validateEnv) insertActivePAT(t *testing.T, orgID string, perms int64) string {
	t.Helper()
	tokenID := uuid.New()
	bearer := "ibex_pat_" + tokenID.String() + "_integrationsecret"
	prefix := "ibex_pat_" + tokenID.String()
	hash := e.mustHash(t, bearer)
	_, err := e.repo.InsertTestToken(context.Background(), orgID, prefix, hash, "test-pat", perms, false, nil)
	if err != nil {
		t.Fatalf("insert token: %v", err)
	}
	return bearer
}

func (e validateEnv) assertValidateOK(t *testing.T, orgID string, perms int64) {
	t.Helper()
	bearer := e.insertActivePAT(t, orgID, perms)
	resp, err := e.v.Validate(context.Background(), bearer)
	if err != nil {
		t.Fatalf("validate: %v", err)
	}
	if resp.GetOrgId() != orgID {
		t.Fatalf("org=%s want %s", resp.GetOrgId(), orgID)
	}
	if resp.GetPermissions() != perms {
		t.Fatalf("perms=%d want %d", resp.GetPermissions(), perms)
	}
}

func (e validateEnv) assertUnauthenticated(t *testing.T, bearer string) {
	t.Helper()
	_, err := e.v.Validate(context.Background(), bearer)
	if !errors.Is(err, token.ErrUnauthenticated) {
		t.Fatalf("expected unauthenticated, got %v", err)
	}
}

func (e validateEnv) assertRevokedRejected(t *testing.T, orgID string) {
	t.Helper()
	revokedID := uuid.New()
	revokedBearer := "ibex_pat_" + revokedID.String() + "_revoked"
	revokedHash := e.mustHash(t, revokedBearer)
	_, err := e.repo.InsertTestToken(context.Background(), orgID, "ibex_pat_"+revokedID.String(), revokedHash, "revoked", 1, true, nil)
	if err != nil {
		t.Fatalf("insert revoked: %v", err)
	}
	e.assertUnauthenticated(t, revokedBearer)
}

func (e validateEnv) assertValidateOrg(t *testing.T, orgID string, perms int64) {
	t.Helper()
	bearer := e.insertActivePAT(t, orgID, perms)
	resp, err := e.v.Validate(context.Background(), bearer)
	if err != nil {
		t.Fatalf("validate org: %v", err)
	}
	if resp.GetOrgId() != orgID {
		t.Fatalf("org id: got %s want %s", resp.GetOrgId(), orgID)
	}
}

func (e validateEnv) assertOptionalFields(t *testing.T, orgID, userID, agentID string) {
	t.Helper()
	tokenID := uuid.New()
	bearer := "ibex_pat_" + tokenID.String() + "_optionalfields"
	prefix := "ibex_pat_" + tokenID.String()
	hash := e.mustHash(t, bearer)
	expires := token.FutureExpiry()
	_, err := e.repo.CreateToken(context.Background(), repository.CreateTokenParams{
		ID: tokenID.String(), OrgID: orgID, Name: "scoped-pat",
		Hash: hash, Prefix: prefix, Permissions: 55,
		UserID: &userID, AgentID: &agentID, ExpiresAt: expires,
	})
	if err != nil {
		t.Fatalf("insert scoped token: %v", err)
	}
	resp, err := e.v.Validate(context.Background(), bearer)
	if err != nil {
		t.Fatalf("validate: %v", err)
	}
	assertEqualString(t, "user_id", resp.GetUserId(), userID)
	assertEqualString(t, "agent_id", resp.GetAgentId(), agentID)
	assertExpiresMatches(t, resp.GetExpiresAt(), expires)
}

func assertEqualString(t *testing.T, label, got, want string) {
	t.Helper()
	if got != want {
		t.Fatalf("%s: got %q want %q", label, got, want)
	}
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
