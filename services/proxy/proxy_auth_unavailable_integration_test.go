//go:build integration

package proxy_test

import (
	"net/http"
	"testing"

	"github.com/Rick1330/ibex-harness/infra/testing/testutil"
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
	validBearer, _ := testutil.SeedToken(t, db, orgID, 42)

	authFx.Close()

	req, _ := http.NewRequest(http.MethodGet, srv.URL+"/v1/internal/auth-probe", nil)
	req.Header.Set("Authorization", "Bearer "+validBearer)
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusServiceUnavailable {
		t.Fatalf("status: %d body=%s", resp.StatusCode, readBody(resp))
	}
	srv.Close()
}
