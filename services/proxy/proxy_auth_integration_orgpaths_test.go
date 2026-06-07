//go:build integration

package proxy_test

import (
	"net/http"
	"testing"
)

func TestProxyAuthIntegration_OrgPaths(t *testing.T) {
	fx := setupProxyAuthFixture(t)

	t.Run("cross tenant path", func(t *testing.T) {
		resp, _ := orgAuthProbeGET(t, orgAuthProbeOpts{srvURL: fx.srv.URL, orgID: fx.orgB, bearer: fx.validBearer})
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusForbidden {
			t.Fatalf("status: %d", resp.StatusCode)
		}
	})

	t.Run("matching org path", func(t *testing.T) {
		resp, _ := orgAuthProbeGET(t, orgAuthProbeOpts{
			srvURL: fx.srv.URL, orgID: fx.orgA, bearer: fx.validBearer, agentID: fx.agentA,
		})
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusOK {
			t.Fatalf("status: %d", resp.StatusCode)
		}
	})

	t.Run("invalid org path uuid", func(t *testing.T) {
		resp, _ := orgAuthProbeGET(t, orgAuthProbeOpts{srvURL: fx.srv.URL, orgID: "not-a-uuid", bearer: fx.validBearer})
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusBadRequest {
			t.Fatalf("status: %d body=%s", resp.StatusCode, readBody(resp))
		}
	})

	t.Run("org b token on org b path", func(t *testing.T) {
		resp, _ := orgAuthProbeGET(t, orgAuthProbeOpts{
			srvURL: fx.srv.URL, orgID: fx.orgB, bearer: fx.orgBBearer, agentID: fx.agentB,
		})
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusOK {
			t.Fatalf("status: %d", resp.StatusCode)
		}
	})
}
