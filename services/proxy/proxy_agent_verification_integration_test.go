//go:build integration

package proxy_test

import (
	"net/http"
	"strings"
	"testing"

	"github.com/Rick1330/ibex-harness/infra/testing/testutil"
	"github.com/Rick1330/ibex-harness/services/auth/integrationtest"
	"github.com/google/uuid"
)

func TestProxyAgentVerificationIntegration(t *testing.T) {
	dsn, cleanup := testutil.SetupPostgres(t)
	defer cleanup()

	db := testutil.OpenDB(t, dsn)
	defer db.Close()

	authFx := integrationtest.StartAuthGRPC(t, dsn)
	defer authFx.Close()

	orgA := testutil.SeedOrganization(t, db, "Org A", "org-a-agent-"+uuid.NewString()[:8])
	orgB := testutil.SeedOrganization(t, db, "Org B", "org-b-agent-"+uuid.NewString()[:8])
	userA := testutil.SeedUser(t, db, orgA, "user-a-"+uuid.NewString()[:8]+"@example.com", "User A")
	userB := testutil.SeedUser(t, db, orgB, "user-b-"+uuid.NewString()[:8]+"@example.com", "User B")
	agentA := testutil.SeedAgent(t, db, orgA, userA, "Agent A", "agent-a-"+uuid.NewString()[:8])
	agentB := testutil.SeedAgent(t, db, orgB, userB, "Agent B", "agent-b-"+uuid.NewString()[:8])
	validBearer, _ := testutil.SeedToken(t, db, orgA, 42)

	srv := startProxyServer(t, authFx.Addr, proxyServerOpts{})
	defer srv.Close()

	t.Run("missing agent header", func(t *testing.T) {
		resp, body := authProbeGET(t, authProbeOpts{srvURL: srv.URL, bearer: validBearer})
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusBadRequest || !strings.Contains(body, "MISSING_AGENT_ID") {
			t.Fatalf("status=%d body=%s", resp.StatusCode, body)
		}
	})

	t.Run("cross tenant rejected", func(t *testing.T) {
		resp, body := authProbeGET(t, authProbeOpts{srvURL: srv.URL, bearer: validBearer, agentID: agentB})
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusForbidden || !strings.Contains(body, "AGENT_NOT_AUTHORIZED") {
			t.Fatalf("status=%d body=%s", resp.StatusCode, body)
		}
	})

	t.Run("own agent allowed", func(t *testing.T) {
		resp, _ := authProbeGET(t, authProbeOpts{srvURL: srv.URL, bearer: validBearer, agentID: agentA})
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusOK {
			t.Fatalf("status=%d", resp.StatusCode)
		}
	})

	t.Run("paused agent rejected", func(t *testing.T) {
		pausedID := seedPausedAgent(t, db, orgA, userA)
		resp, body := authProbeGET(t, authProbeOpts{srvURL: srv.URL, bearer: validBearer, agentID: pausedID})
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusForbidden || !strings.Contains(body, "AGENT_SUSPENDED") {
			t.Fatalf("status=%d body=%s", resp.StatusCode, body)
		}
	})
}
