//go:build integration

package auth_test

import (
	"context"
	"errors"
	"testing"

	"github.com/Rick1330/ibex-harness/infra/testing/testutil"
	"github.com/Rick1330/ibex-harness/services/auth/internal/repository"
	"github.com/Rick1330/ibex-harness/services/auth/internal/token"
	"github.com/google/uuid"
)

func TestValidateTokenIntegration(t *testing.T) {
	dsn, cleanup := testutil.SetupPostgres(t)
	defer cleanup()

	db := testutil.OpenDB(t, dsn)
	defer db.Close()

	repo := repository.NewTokensRepository(db)
	argon2 := token.DefaultArgon2Params()
	validator := token.NewValidator(repo, argon2)

	orgA := testutil.SeedOrganization(t, db, "Org A", "org-a-val-"+uuid.NewString()[:8])
	orgB := testutil.SeedOrganization(t, db, "Org B", "org-b-val-"+uuid.NewString()[:8])

	tokenID := uuid.New()
	bearer := "ibex_pat_" + tokenID.String() + "_integrationsecret"
	prefix := "ibex_pat_" + tokenID.String()
	hash, err := token.HashForTest(bearer, argon2)
	if err != nil {
		t.Fatalf("hash: %v", err)
	}
	_, err = repo.InsertTestToken(context.Background(), orgA, prefix, hash, "test-pat", 42, false, nil)
	if err != nil {
		t.Fatalf("insert token: %v", err)
	}

	resp, err := validator.Validate(context.Background(), bearer)
	if err != nil {
		t.Fatalf("validate: %v", err)
	}
	if resp.GetOrgId() != orgA || resp.GetPermissions() != 42 {
		t.Fatalf("response: org=%s perms=%d", resp.GetOrgId(), resp.GetPermissions())
	}

	_, err = validator.Validate(context.Background(), bearer+"wrong")
	if !errors.Is(err, token.ErrUnauthenticated) {
		t.Fatalf("expected unauthenticated, got %v", err)
	}

	revokedID := uuid.New()
	revokedBearer := "ibex_pat_" + revokedID.String() + "_revoked"
	revokedHash, err := token.HashForTest(revokedBearer, argon2)
	if err != nil {
		t.Fatalf("hash revoked: %v", err)
	}
	_, err = repo.InsertTestToken(context.Background(), orgA, "ibex_pat_"+revokedID.String(), revokedHash, "revoked", 1, true, nil)
	if err != nil {
		t.Fatalf("insert revoked: %v", err)
	}
	_, err = validator.Validate(context.Background(), revokedBearer)
	if !errors.Is(err, token.ErrUnauthenticated) {
		t.Fatalf("revoked token should fail: %v", err)
	}

	otherID := uuid.New()
	otherBearer := "ibex_pat_" + otherID.String() + "_otherorg"
	otherHash, err := token.HashForTest(otherBearer, argon2)
	if err != nil {
		t.Fatalf("hash other: %v", err)
	}
	_, err = repo.InsertTestToken(context.Background(), orgB, "ibex_pat_"+otherID.String(), otherHash, "org-b-token", 99, false, nil)
	if err != nil {
		t.Fatalf("insert org b token: %v", err)
	}

	respB, err := validator.Validate(context.Background(), otherBearer)
	if err != nil {
		t.Fatalf("validate org b: %v", err)
	}
	if respB.GetOrgId() != orgB {
		t.Fatalf("org b id: got %s want %s", respB.GetOrgId(), orgB)
	}
}
