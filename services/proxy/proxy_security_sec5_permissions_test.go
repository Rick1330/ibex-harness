//go:build integration

package proxy_test

import (
	"net/http"
	"strings"
	"testing"

	"github.com/Rick1330/ibex-harness/infra/testing/testutil"
	apierror "github.com/Rick1330/ibex-harness/packages/apierror"
	"github.com/Rick1330/ibex-harness/packages/permissions"
	"github.com/Rick1330/ibex-harness/packages/provider"
)

func TestSecurity_SEC5_1_ZeroPermissions(t *testing.T) {
	env := securityEnv(t)
	zero := testutil.SeedTokenZeroPerms(t, env.db, env.orgA.OrgID)
	requireChat(t, chatRequestOpts{
		srvURL: env.proxy.URL, bearer: zero, agentID: env.orgA.AgentID,
		contentType: "application/json", body: minimalChatBody,
	}, probeExpect{http.StatusForbidden, apierror.CodeInsufficientPermissions}, zero)
}

func TestSecurity_SEC5_2_ReadOnlyOnChat(t *testing.T) {
	env := securityEnv(t)
	readOnly, _ := testutil.SeedToken(t, env.db, env.orgA.OrgID, permissions.ReadOnly)
	requireChat(t, chatRequestOpts{
		srvURL: env.proxy.URL, bearer: readOnly, agentID: env.orgA.AgentID,
		contentType: "application/json", body: minimalChatBody,
	}, probeExpect{http.StatusForbidden, apierror.CodeInsufficientPermissions}, readOnly)
}

func TestSecurity_SEC5_3_FullPermissionsProceeds(t *testing.T) {
	env := setupSecurityTestEnv(t, proxyServerOpts{
		defaultRPM: 60,
		providers:  []provider.Provider{mockForwardingProvider{}},
	})
	chatToken, _ := testutil.SeedToken(t, env.db, env.orgA.OrgID, permissions.ProxyChatCompletion)
	resp, body := chatPOST(t, chatRequestOpts{
		srvURL: env.proxy.URL, bearer: chatToken, agentID: env.orgA.AgentID,
		contentType: "application/json", body: minimalChatBody,
	})
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("status=%d want=200 body=%s", resp.StatusCode, body)
	}
	if !strings.Contains(body, "assistant") {
		t.Fatalf("body=%s", body)
	}
}
