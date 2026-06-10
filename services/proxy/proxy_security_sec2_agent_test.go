//go:build integration

package proxy_test

import (
	"net/http"
	"testing"

	"github.com/Rick1330/ibex-harness/infra/testing/testutil"
	"github.com/google/uuid"
)

func TestSecurity_SEC2_1_MissingAgentID(t *testing.T) {
	env := securityEnv(t)
	requireProbe(t, authProbeOpts{srvURL: env.proxy.URL, bearer: env.orgA.Token},
		probeExpect{http.StatusBadRequest, "MISSING_AGENT_ID"}, env.orgA.Token)
}

func TestSecurity_SEC2_2_InvalidAgentUUID(t *testing.T) {
	env := securityEnv(t)
	requireProbe(t, authProbeOpts{srvURL: env.proxy.URL, bearer: env.orgA.Token, agentID: "not-a-uuid"},
		probeExpect{http.StatusBadRequest, "VALIDATION_ERROR"}, env.orgA.Token)
}

func TestSecurity_SEC2_3_UnknownAgent(t *testing.T) {
	env := securityEnv(t)
	requireProbe(t, authProbeOpts{srvURL: env.proxy.URL, bearer: env.orgA.Token, agentID: uuid.New().String()},
		probeExpect{http.StatusForbidden, "AGENT_NOT_AUTHORIZED"}, env.orgA.Token)
}

func TestSecurity_SEC2_4_CrossOrgAgent(t *testing.T) {
	env := securityEnv(t)
	requireProbe(t, authProbeOpts{srvURL: env.proxy.URL, bearer: env.orgA.Token, agentID: env.orgB.AgentID},
		probeExpect{http.StatusForbidden, "AGENT_NOT_AUTHORIZED"}, env.orgA.Token)
}

func TestSecurity_SEC2_5_and_6_NonActiveAgents(t *testing.T) {
	env := securityEnv(t)
	cases := []struct {
		name   string
		label  string
		status string
	}{
		{"SEC2_5_PausedAgent", "paused", "paused"},
		{"SEC2_6_ArchivedAgent", "archived", "archived"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			agentID := testutil.SeedAgentWithStatus(t, env.db, env.orgA.OrgID, env.orgA.UserID,
				tc.label, tc.label+"-"+uuid.NewString()[:8], tc.status)
			requireProbe(t, authProbeOpts{srvURL: env.proxy.URL, bearer: env.orgA.Token, agentID: agentID},
				probeExpect{http.StatusForbidden, "AGENT_SUSPENDED"}, env.orgA.Token)
		})
	}
}

func TestSecurity_SEC2_7_ValidAgent(t *testing.T) {
	env := securityEnv(t)
	requireProbeOK(t, orgAProbeOpts(env))
}
