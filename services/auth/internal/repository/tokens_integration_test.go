//go:build integration

package repository_test

import (
	"context"
	"database/sql"
	"errors"
	"testing"

	"github.com/Rick1330/ibex-harness/infra/testing/testutil"
	"github.com/Rick1330/ibex-harness/services/auth/internal/repository"
	"github.com/Rick1330/ibex-harness/services/auth/internal/token"
	"github.com/google/uuid"
)

func TestTokensRepository_CreateToken(t *testing.T) {
	repo, db := setupTokensRepo(t)
	orgID := testutil.SeedOrganization(t, db, "Create Org", "create-"+uuid.NewString()[:8])
	rowID := uuid.New()
	id, err := repo.CreateToken(context.Background(), repository.CreateTokenParams{
		ID: rowID.String(), OrgID: orgID, Name: "integration-create", Description: "desc",
		// A unique hash: tokens.hash is UNIQUE, so a fixed value makes the test
		// fail on the second run against the same database.
		Hash: "hash-" + rowID.String(), Prefix: "ibex_pat_" + rowID.String(), Permissions: 42,
	})
	if err != nil {
		t.Fatalf("CreateToken: %v", err)
	}
	if id != rowID.String() {
		t.Fatalf("id: got %s want %s", id, rowID.String())
	}
}

func TestTokensRepository_RevokeToken_ErrNotFound(t *testing.T) {
	repo, db := setupTokensRepo(t)
	orgID := testutil.SeedOrganization(t, db, "Revoke Org", "revoke-"+uuid.NewString()[:8])
	err := repo.RevokeToken(context.Background(), repository.RevokeTokenInput{OrgID: orgID, TokenID: uuid.NewString()})
	if !errors.Is(err, repository.ErrNotFound) {
		t.Fatalf("expected ErrNotFound, got %v", err)
	}
}

func TestTokensRepository_RevokeToken_HappyPath(t *testing.T) {
	repo, db := setupTokensRepo(t)
	orgID := testutil.SeedOrganization(t, db, "Revoke OK Org", "revoke-ok-"+uuid.NewString()[:8])
	tokenID := uuid.New()
	bearer := "ibex_pat_" + tokenID.String() + "_revokeme"
	prefix := "ibex_pat_" + tokenID.String()
	hash, err := token.HashForTest(bearer, token.DefaultArgon2Params())
	if err != nil {
		t.Fatalf("hash: %v", err)
	}
	id, err := repo.InsertTestToken(context.Background(), repository.TestTokenParams{
		OrgID: orgID, Prefix: prefix, Hash: hash, Name: "revoke-me", Permissions: 1,
	})
	if err != nil {
		t.Fatalf("insert: %v", err)
	}
	if err = repo.RevokeToken(context.Background(), repository.RevokeTokenInput{OrgID: orgID, TokenID: id}); err != nil {
		t.Fatalf("RevokeToken: %v", err)
	}
	_, err = repo.FindActiveByPrefix(context.Background(), prefix)
	if !errors.Is(err, sql.ErrNoRows) {
		t.Fatalf("revoked token should not be active: %v", err)
	}
}
