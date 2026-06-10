//go:build integration

package proxy_test

import (
	"net/http"
	"testing"

	"github.com/Rick1330/ibex-harness/infra/testing/testutil"
	apierror "github.com/Rick1330/ibex-harness/packages/apierror"
	"github.com/Rick1330/ibex-harness/services/auth/integrationtest"
	"github.com/google/uuid"
)

func TestProxyAuthUnavailable(t *testing.T) {
	dsn, cleanup := testutil.SetupPostgres(t)
	defer cleanup()

	db := testutil.OpenDB(t, dsn)
	defer db.Close()

	authFx := integrationtest.StartAuthGRPC(t, dsn)
	srv := startProxyServer(t, authFx.Addr, proxyServerOpts{})

	orgID := testutil.SeedOrganization(t, db, "Org", "org-down-"+uuid.NewString()[:8])
	userID := testutil.SeedUser(t, db, orgID, "u-"+uuid.NewString()[:8]+"@example.com", "User")
	agentID := testutil.SeedAgent(t, db, orgID, userID, "Agent", "agent-"+uuid.NewString()[:8])
	validBearer, _ := testutil.SeedToken(t, db, orgID, 42)

	authFx.Close()

	resp, body := authProbeGET(t, authProbeOpts{srvURL: srv.URL, bearer: validBearer, agentID: agentID})
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusServiceUnavailable {
		t.Fatalf("status: %d body=%s", resp.StatusCode, body)
	}
	requireErrorCode(t, body, apierror.CodeServiceDegraded)
	assertSecurityErrorEnvelope(t, resp, body, validBearer)
	srv.Close()
}
