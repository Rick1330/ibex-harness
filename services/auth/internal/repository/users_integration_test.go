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
	t.Parallel()
	dsn, cleanupPG := testutil.SetupPostgres(t)
	defer cleanupPG()

	db := testutil.OpenDB(t, dsn)
	defer func() { _ = db.Close() }()

	label := uuid.NewString()[:8]
	orgA := testutil.SeedOrganization(t, db, "User Org A "+label, "user-a-"+label)
	orgB := testutil.SeedOrganization(t, db, "User Org B "+label, "user-b-"+label)
	userA := testutil.SeedUser(t, db, orgA, "user-a-"+label+"@test.local", "User A")

	fx := userLookupFixture{
		t: t, repo: repository.NewUsersRepository(db, nil), ctx: context.Background(),
	}
	fx.assertSameOrg(userA, orgA)
	fx.assertMiss(userA, orgB, "cross-org")
	fx.assertMiss(uuid.NewString(), orgA, "unknown-user")
}

type userLookupFixture struct {
	t    *testing.T
	repo *repository.UsersRepository
	ctx  context.Context
}

func (f userLookupFixture) assertSameOrg(userID, orgID string) {
	f.t.Helper()
	rec, err := f.repo.GetByIDAndOrg(f.ctx, uuid.MustParse(userID), uuid.MustParse(orgID))
	if err != nil {
		f.t.Fatalf("same-org: %v", err)
	}
	if rec == nil {
		f.t.Fatal("same-org: nil record")
	}
	if rec.ID != userID {
		f.t.Fatalf("id=%q want %q", rec.ID, userID)
	}
	if rec.OrgID != orgID {
		f.t.Fatalf("org=%q want %q", rec.OrgID, orgID)
	}
}

func (f userLookupFixture) assertMiss(userID, orgID, label string) {
	f.t.Helper()
	miss, err := f.repo.GetByIDAndOrg(f.ctx, uuid.MustParse(userID), uuid.MustParse(orgID))
	if err != nil {
		f.t.Fatalf("%s: %v", label, err)
	}
	if miss != nil {
		f.t.Fatalf("%s want nil got %+v", label, miss)
	}
}
