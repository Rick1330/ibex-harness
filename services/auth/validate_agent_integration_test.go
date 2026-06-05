//go:build integration

package auth_test

import (
	"context"
	"database/sql"
	"testing"

	"github.com/Rick1330/ibex-harness/infra/testing/testutil"
	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"github.com/Rick1330/ibex-harness/services/auth/internal/repository"
	"github.com/google/uuid"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

func TestValidateAgentIntegration_OKAndSecurity(t *testing.T) {
	dsn, cleanupPG := testutil.SetupPostgres(t)
	defer cleanupPG()

	db := testutil.OpenDB(t, dsn)
	defer db.Close()

	orgA := testutil.SeedOrganization(t, db, "Org A", "org-a-val-"+uuid.NewString()[:8])
	orgB := testutil.SeedOrganization(t, db, "Org B", "org-b-val-"+uuid.NewString()[:8])

	userA := testutil.SeedUser(t, db, orgA, "user-a-"+uuid.NewString()[:8]+"@example.com", "User A")
	userB := testutil.SeedUser(t, db, orgB, "user-b-"+uuid.NewString()[:8]+"@example.com", "User B")

	agentA := testutil.SeedAgent(t, db, orgA, userA, "Agent A", "agent-a-"+uuid.NewString()[:8])
	agentB := testutil.SeedAgent(t, db, orgB, userB, "Agent B", "agent-b-"+uuid.NewString()[:8])

	// Seed an inactive agent in Org A to verify non-active rejection.
	inactiveAgentID := uuid.New().String()
	if err := testutil.WithServiceAccount(context.Background(), db, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(context.Background(), `
			INSERT INTO ibex_core.agents (id, org_id, created_by, name, slug, status)
			VALUES ($1::uuid, $2::uuid, $3::uuid, $4, $5, 'paused')`,
			inactiveAgentID, orgA, userA, "Agent Inactive", "agent-inactive-"+uuid.NewString()[:8],
		)
		return err
	}); err != nil {
		t.Fatalf("seed inactive agent: %v", err)
	}

	client, cleanup := startAuthGRPC(t, dsn)
	defer cleanup()

	adminBearerA := testutil.SeedBootstrapAdminToken(t, db, orgA)
	ctx := authCtx(adminBearerA)

	// OK (active agent, same org)
	okResp, err := client.ValidateAgent(ctx, &authv1.ValidateAgentRequest{
		AgentId: agentA,
		OrgId:   orgA,
	})
	if err != nil {
		t.Fatalf("ValidateAgent OK err: %v", err)
	}
	if okResp.GetAgentId() != agentA || okResp.GetOrgId() != orgA || okResp.GetStatus() != "active" {
		t.Fatalf("ValidateAgent OK response mismatch: %+v", okResp)
	}

	// Cross-org attempt must be PERMISSION_DENIED (not NOT_FOUND)
	_, err = client.ValidateAgent(ctx, &authv1.ValidateAgentRequest{
		AgentId: agentB,
		OrgId:   orgA,
	})
	if status.Code(err) != codes.PermissionDenied {
		t.Fatalf("cross-org code: %v", status.Code(err))
	}

	// Inactive agent must be PERMISSION_DENIED
	_, err = client.ValidateAgent(ctx, &authv1.ValidateAgentRequest{
		AgentId: inactiveAgentID,
		OrgId:   orgA,
	})
	if status.Code(err) != codes.PermissionDenied {
		t.Fatalf("inactive code: %v", status.Code(err))
	}
}

// Compile-time reference to ensure repository types remain reachable.
var _ = repository.AgentRecord{}
