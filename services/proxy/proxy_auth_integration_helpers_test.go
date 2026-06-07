//go:build integration

package proxy_test

import (
	"database/sql"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/Rick1330/ibex-harness/infra/testing/testutil"
	"github.com/Rick1330/ibex-harness/packages/permissions"
	"github.com/Rick1330/ibex-harness/services/auth/integrationtest"
	"github.com/google/uuid"
)

type proxyAuthFixture struct {
	db             *sql.DB
	authFx         *integrationtest.AuthGRPCFixture
	srv            *httptest.Server
	orgA           string
	orgB           string
	agentA         string
	agentB         string
	validBearer    string
	chatBearer     string
	revokedBearer  string
	orgBBearer     string
	lowPermsBearer string
}

func setupProxyAuthFixture(t *testing.T) proxyAuthFixture {
	t.Helper()
	dsn, cleanup := testutil.SetupPostgres(t)
	t.Cleanup(cleanup)

	db := testutil.OpenDB(t, dsn)
	t.Cleanup(func() { _ = db.Close() })

	authFx := integrationtest.StartAuthGRPC(t, dsn)
	t.Cleanup(authFx.Close)

	orgA := testutil.SeedOrganization(t, db, "Org A", "org-a-proxy-"+uuid.NewString()[:8])
	orgB := testutil.SeedOrganization(t, db, "Org B", "org-b-proxy-"+uuid.NewString()[:8])
	userA := testutil.SeedUser(t, db, orgA, "user-a-"+uuid.NewString()[:8]+"@example.com", "User A")
	userB := testutil.SeedUser(t, db, orgB, "user-b-"+uuid.NewString()[:8]+"@example.com", "User B")
	agentA := testutil.SeedAgent(t, db, orgA, userA, "Agent A", "agent-a-"+uuid.NewString()[:8])
	agentB := testutil.SeedAgent(t, db, orgB, userB, "Agent B", "agent-b-"+uuid.NewString()[:8])

	validBearer, _ := testutil.SeedToken(t, db, orgA, 42)
	chatBearer, _ := testutil.SeedToken(t, db, orgA, permissions.ProxyChatCompletion)
	revokedBearer := testutil.SeedTokenRevoked(t, db, orgA, uuid.New(), 42)
	orgBBearer, _ := testutil.SeedToken(t, db, orgB, 42)
	lowPermsBearer, _ := testutil.SeedToken(t, db, orgA, permissions.ReadOnly)

	srv := startProxyServer(t, authFx.Addr)
	t.Cleanup(srv.Close)

	return proxyAuthFixture{
		db: db, authFx: authFx, srv: srv,
		orgA: orgA, orgB: orgB, agentA: agentA, agentB: agentB,
		validBearer: validBearer, chatBearer: chatBearer, revokedBearer: revokedBearer,
		orgBBearer: orgBBearer, lowPermsBearer: lowPermsBearer,
	}
}

func chatPOST(t *testing.T, srvURL, bearer, agentID, contentType, body string) (*http.Response, string) {
	t.Helper()
	req, err := http.NewRequest(http.MethodPost, srvURL+"/v1/chat/completions", strings.NewReader(body))
	if err != nil {
		t.Fatal(err)
	}
	if bearer != "" {
		req.Header.Set("Authorization", "Bearer "+bearer)
	}
	if contentType != "" {
		req.Header.Set("Content-Type", contentType)
	}
	if agentID != "" {
		req.Header.Set("X-IBEX-Agent-ID", agentID)
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	b, _ := io.ReadAll(resp.Body)
	return resp, string(b)
}

func orgAuthProbeGET(t *testing.T, srvURL, orgID, bearer, agentID string) (*http.Response, string) {
	t.Helper()
	req, err := http.NewRequest(http.MethodGet, srvURL+"/v1/orgs/"+orgID+"/auth-probe", nil)
	if err != nil {
		t.Fatal(err)
	}
	if bearer != "" {
		req.Header.Set("Authorization", "Bearer "+bearer)
	}
	if agentID != "" {
		req.Header.Set("X-IBEX-Agent-ID", agentID)
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	b, _ := io.ReadAll(resp.Body)
	return resp, string(b)
}
