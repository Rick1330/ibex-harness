//go:build integration

package proxy_test

import (
	"net/http"
	"strings"
	"testing"

	"github.com/Rick1330/ibex-harness/infra/testing/testutil"
	"github.com/Rick1330/ibex-harness/packages/permissions"
)

func TestSecurity_SEC5_1_ZeroPermissions(t *testing.T) {
	env := securityEnv(t)
	zero := testutil.SeedTokenZeroPerms(t, env.db, env.orgA.OrgID)
	resp, body := chatPOST(t, chatRequestOpts{
		srvURL: env.proxy.URL, bearer: zero, agentID: env.orgA.AgentID,
		contentType: "application/json", body: minimalChatBody,
	})
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusForbidden || !strings.Contains(body, "INSUFFICIENT_PERMISSIONS") {
		t.Fatalf("status=%d body=%s", resp.StatusCode, body)
	}
	assertSecurityErrorEnvelope(t, resp, body, zero)
}

func TestSecurity_SEC5_2_ReadOnlyOnChat(t *testing.T) {
	env := securityEnv(t)
	readOnly, _ := testutil.SeedToken(t, env.db, env.orgA.OrgID, permissions.ReadOnly)
	resp, body := chatPOST(t, chatRequestOpts{
		srvURL: env.proxy.URL, bearer: readOnly, agentID: env.orgA.AgentID,
		contentType: "application/json", body: minimalChatBody,
	})
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusForbidden || !strings.Contains(body, "INSUFFICIENT_PERMISSIONS") {
		t.Fatalf("status=%d body=%s", resp.StatusCode, body)
	}
	assertSecurityErrorEnvelope(t, resp, body, readOnly)
}

func TestSecurity_SEC5_3_FullPermissionsProceeds(t *testing.T) {
	env := securityEnv(t)
	chatToken, _ := testutil.SeedToken(t, env.db, env.orgA.OrgID, permissions.ProxyChatCompletion)
	resp, body := chatPOST(t, chatRequestOpts{
		srvURL: env.proxy.URL, bearer: chatToken, agentID: env.orgA.AgentID,
		contentType: "application/json", body: minimalChatBody,
	})
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusNotImplemented || !strings.Contains(body, "PROVIDER_NOT_CONFIGURED") {
		t.Fatalf("status=%d body=%s", resp.StatusCode, body)
	}
	assertSecurityErrorEnvelope(t, resp, body, chatToken)
}
