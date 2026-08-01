//go:build integration

package repository_test

import (
	"context"
	"testing"

	"github.com/Rick1330/ibex-harness/infra/testing/testutil"
	"github.com/Rick1330/ibex-harness/services/auth/internal/repository"
	"github.com/google/uuid"
)

func TestUsersRepository_GetByIDAndOrg(t *testing.T) {
	dsn, cleanupPG := testutil.SetupPostgres(t)
	defer cleanupPG()

	db := testutil.OpenDB(t, dsn)
	defer func() { _ = db.Close() }()

	label := uuid.NewString()[:8]
	orgA := testutil.SeedOrganization(t, db, "User Org A "+label, "user-a-"+label)
	orgB := testutil.SeedOrganization(t, db, "User Org B "+label, "user-b-"+label)
	userA := testutil.SeedUser(t, db, orgA, "user-a-"+label+"@test.local", "User A")

	repo := repository.NewUsersRepository(db, nil)
	ctx := context.Background()

	assertUserSameOrg(t, repo, ctx, userA, orgA)
	assertUserCrossOrgNil(t, repo, ctx, userA, orgB)
	assertUserUnknownNil(t, repo, ctx, orgA)
}

func assertUserSameOrg(t *testing.T, repo *repository.UsersRepository, ctx context.Context, userID, orgID string) {
	t.Helper()
	rec, err := repo.GetByIDAndOrg(ctx, uuid.MustParse(userID), uuid.MustParse(orgID))
	if err != nil {
		t.Fatalf("same-org: %v", err)
	}
	if rec == nil {
		t.Fatal("same-org: nil record")
	}
	if rec.ID != userID {
		t.Fatalf("id=%q want %q", rec.ID, userID)
	}
	if rec.OrgID != orgID {
		t.Fatalf("org=%q want %q", rec.OrgID, orgID)
	}
}

func assertUserCrossOrgNil(t *testing.T, repo *repository.UsersRepository, ctx context.Context, userID, otherOrg string) {
	t.Helper()
	miss, err := repo.GetByIDAndOrg(ctx, uuid.MustParse(userID), uuid.MustParse(otherOrg))
	if err != nil {
		t.Fatalf("cross-org: %v", err)
	}
	if miss != nil {
		t.Fatalf("cross-org want nil got %+v", miss)
	}
}

func assertUserUnknownNil(t *testing.T, repo *repository.UsersRepository, ctx context.Context, orgID string) {
	t.Helper()
	miss, err := repo.GetByIDAndOrg(ctx, uuid.New(), uuid.MustParse(orgID))
	if err != nil {
		t.Fatalf("unknown user: %v", err)
	}
	if miss != nil {
		t.Fatalf("unknown user want nil got %+v", miss)
	}
}
