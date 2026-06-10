//go:build integration

package proxy_test

import (
	"net/http"
	"testing"

	"github.com/Rick1330/ibex-harness/infra/testing/testutil"
	apierror "github.com/Rick1330/ibex-harness/packages/apierror"
	"github.com/Rick1330/ibex-harness/packages/permissions"
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
	env := securityEnv(t)
	chatToken, _ := testutil.SeedToken(t, env.db, env.orgA.OrgID, permissions.ProxyChatCompletion)
	requireChat(t, chatRequestOpts{
		srvURL: env.proxy.URL, bearer: chatToken, agentID: env.orgA.AgentID,
		contentType: "application/json", body: minimalChatBody,
	}, probeExpect{http.StatusNotImplemented, apierror.CodeProviderNotConfigured}, chatToken)
}
