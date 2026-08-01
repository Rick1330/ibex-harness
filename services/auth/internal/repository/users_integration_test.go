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

	rec, err := repo.GetByIDAndOrg(ctx, uuid.MustParse(userA), uuid.MustParse(orgA))
	if err != nil {
		t.Fatalf("same-org: %v", err)
	}
	if rec == nil || rec.ID != userA || rec.OrgID != orgA {
		t.Fatalf("same-org record=%+v", rec)
	}

	miss, err := repo.GetByIDAndOrg(ctx, uuid.MustParse(userA), uuid.MustParse(orgB))
	if err != nil {
		t.Fatalf("cross-org: %v", err)
	}
	if miss != nil {
		t.Fatalf("cross-org want nil got %+v", miss)
	}
}
