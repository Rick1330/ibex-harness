//go:build integration

package proxy_test

import (
	"context"
	"database/sql"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/infra/testing/testutil"
	apierror "github.com/Rick1330/ibex-harness/packages/apierror"
)

// pauseAgentInDB mirrors services/api pause_agent SQL (status active → paused).
// Security-integration CI has Postgres+auth+proxy only — no Python API process —
// so this test applies the same UPDATE the management API uses.
func pauseAgentInDB(t *testing.T, db *sql.DB, orgID, agentID string) {
	t.Helper()
	ctx := context.Background()
	err := testutil.WithServiceAccount(ctx, db, func(tx *sql.Tx) error {
		res, err := tx.ExecContext(ctx, `
			UPDATE ibex_core.agents
			SET status = 'paused'
			WHERE id = $1::uuid
			  AND org_id = $2::uuid
			  AND deleted_at IS NULL
			  AND status = 'active'`, agentID, orgID)
		if err != nil {
			return err
		}
		n, err := res.RowsAffected()
		if err != nil {
			return err
		}
		if n != 1 {
			t.Fatalf("pause agent: expected 1 row updated, got %d", n)
		}
		return nil
	})
	if err != nil {
		t.Fatalf("pause agent: %v", err)
	}
}

// TestSecurity_SEC7_6_AgentPausePropagatesWithin5s exercises the milestone 4.A.3
// success signal: after an agent is paused (same SQL as POST /v1/agents/{id}/pause),
// auth-probe returns AGENT_SUSPENDED within 5s. ValidateAgent is live (uncached),
// so propagation is a DB visibility bound rather than cache invalidation.
func TestSecurity_SEC7_6_AgentPausePropagatesWithin5s(t *testing.T) {
	env := setupSecurityTestEnv(t, proxyServerOpts{defaultRPM: 60})
	opts := orgAProbeOpts(env)

	requireProbeOK(t, opts)

	start := time.Now()
	pauseAgentInDB(t, env.db, env.orgA.OrgID, env.orgA.AgentID)
	requireProbeForbiddenEventually(t, probeForbiddenOpts{
		opts:   opts,
		secret: env.orgA.Token,
		want:   apierror.CodeAgentSuspended,
		within: productSuspensionSLA,
	})
	elapsed := time.Since(start)
	t.Logf(
		"agent_pause_propagation_latency_ms=%d (limit_ms=%d)",
		elapsed.Milliseconds(),
		productSuspensionSLA.Milliseconds(),
	)
	if elapsed > productSuspensionSLA {
		t.Fatalf("agent pause SLA exceeded: %v (limit %v)", elapsed, productSuspensionSLA)
	}
}
