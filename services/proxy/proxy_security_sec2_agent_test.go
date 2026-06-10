//go:build integration

package proxy_test

import (
	"net/http"
	"testing"

	"github.com/Rick1330/ibex-harness/infra/testing/testutil"
	apierror "github.com/Rick1330/ibex-harness/packages/apierror"
	"github.com/google/uuid"
)

func TestSecurity_SEC2_1_MissingAgentID(t *testing.T) {
	env := securityEnv(t)
	requireProbe(t, authProbeOpts{srvURL: env.proxy.URL, bearer: env.orgA.Token},
		probeExpect{http.StatusBadRequest, apierror.CodeMissingAgentID}, env.orgA.Token)
}

func TestSecurity_SEC2_2_InvalidAgentUUID(t *testing.T) {
	env := securityEnv(t)
	requireProbe(t, authProbeOpts{srvURL: env.proxy.URL, bearer: env.orgA.Token, agentID: "not-a-uuid"},
		probeExpect{http.StatusBadRequest, apierror.CodeValidationError}, env.orgA.Token)
}

func TestSecurity_SEC2_3_UnknownAgent(t *testing.T) {
	env := securityEnv(t)
	requireProbe(t, authProbeOpts{srvURL: env.proxy.URL, bearer: env.orgA.Token, agentID: uuid.New().String()},
		probeExpect{http.StatusForbidden, apierror.CodeAgentNotAuthorized}, env.orgA.Token)
}

func TestSecurity_SEC2_4_CrossOrgAgent(t *testing.T) {
	env := securityEnv(t)
	requireProbe(t, authProbeOpts{srvURL: env.proxy.URL, bearer: env.orgA.Token, agentID: env.orgB.AgentID},
		probeExpect{http.StatusForbidden, apierror.CodeAgentNotAuthorized}, env.orgA.Token)
}

func TestSecurity_SEC2_5_6_7_NonActiveAndValidAgents(t *testing.T) {
	env := securityEnv(t)
	cases := []struct {
		name   string
		label  string
		status string
		code   apierror.Code
	}{
		{"SEC2_5_PausedAgent", "paused", "paused", apierror.CodeAgentSuspended},
		{"SEC2_6_ArchivedAgent", "archived", "archived", apierror.CodeAgentSuspended},
		{"SEC2_6b_SuspendedAgent", "suspended", "suspended", apierror.CodeAgentSuspended},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			agentID := testutil.SeedAgentWithStatus(t, env.db, env.orgA.OrgID, env.orgA.UserID,
				tc.label, tc.label+"-"+uuid.NewString()[:8], tc.status)
			requireProbe(t, authProbeOpts{srvURL: env.proxy.URL, bearer: env.orgA.Token, agentID: agentID},
				probeExpect{http.StatusForbidden, tc.code}, env.orgA.Token)
		})
	}
}

func TestSecurity_SEC2_7_ValidAgent(t *testing.T) {
	env := securityEnv(t)
	requireProbeOK(t, orgAProbeOpts(env))
}

func TestSecurity_SEC2_8_AuthUnavailableWithAgent(t *testing.T) {
	env := securityEnv(t)
	env.authFx.Close()
	requireProbe(t, orgAProbeOpts(env),
		probeExpect{http.StatusServiceUnavailable, apierror.CodeServiceDegraded}, env.orgA.Token)
}
