//go:build integration

package proxy_test

import (
	"net/http"
	"strings"
	"testing"

	"github.com/Rick1330/ibex-harness/infra/testing/testutil"
	"github.com/google/uuid"
)

func TestSecurity_SEC2_1_MissingAgentID(t *testing.T) {
	env := securityEnv(t)
	resp, body := authProbeGET(t, authProbeOpts{srvURL: env.proxy.URL, bearer: env.orgA.Token})
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusBadRequest || !strings.Contains(body, "MISSING_AGENT_ID") {
		t.Fatalf("status=%d body=%s", resp.StatusCode, body)
	}
	assertSecurityErrorEnvelope(t, resp, body, env.orgA.Token)
}

func TestSecurity_SEC2_2_InvalidAgentUUID(t *testing.T) {
	env := securityEnv(t)
	resp, body := authProbeGET(t, authProbeOpts{srvURL: env.proxy.URL, bearer: env.orgA.Token, agentID: "not-a-uuid"})
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusBadRequest || !strings.Contains(body, "VALIDATION_ERROR") {
		t.Fatalf("status=%d body=%s", resp.StatusCode, body)
	}
	assertSecurityErrorEnvelope(t, resp, body, env.orgA.Token)
}

func TestSecurity_SEC2_3_UnknownAgent(t *testing.T) {
	env := securityEnv(t)
	resp, body := authProbeGET(t, authProbeOpts{srvURL: env.proxy.URL, bearer: env.orgA.Token, agentID: uuid.New().String()})
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusForbidden || !strings.Contains(body, "AGENT_NOT_AUTHORIZED") {
		t.Fatalf("status=%d body=%s", resp.StatusCode, body)
	}
	assertSecurityErrorEnvelope(t, resp, body, env.orgA.Token)
}

func TestSecurity_SEC2_4_CrossOrgAgent(t *testing.T) {
	env := securityEnv(t)
	resp, body := authProbeGET(t, authProbeOpts{srvURL: env.proxy.URL, bearer: env.orgA.Token, agentID: env.orgB.AgentID})
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusForbidden || !strings.Contains(body, "AGENT_NOT_AUTHORIZED") {
		t.Fatalf("status=%d body=%s", resp.StatusCode, body)
	}
	assertSecurityErrorEnvelope(t, resp, body, env.orgA.Token)
}

func TestSecurity_SEC2_5_PausedAgent(t *testing.T) {
	env := securityEnv(t)
	paused := testutil.SeedAgentWithStatus(t, env.db, env.orgA.OrgID, env.orgA.UserID, "Paused", "paused-"+uuid.NewString()[:8], "paused")
	resp, body := authProbeGET(t, authProbeOpts{srvURL: env.proxy.URL, bearer: env.orgA.Token, agentID: paused})
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusForbidden || !strings.Contains(body, "AGENT_SUSPENDED") {
		t.Fatalf("status=%d body=%s", resp.StatusCode, body)
	}
	assertSecurityErrorEnvelope(t, resp, body, env.orgA.Token)
}

func TestSecurity_SEC2_6_ArchivedAgent(t *testing.T) {
	env := securityEnv(t)
	archived := testutil.SeedAgentWithStatus(t, env.db, env.orgA.OrgID, env.orgA.UserID, "Archived", "archived-"+uuid.NewString()[:8], "archived")
	resp, body := authProbeGET(t, authProbeOpts{srvURL: env.proxy.URL, bearer: env.orgA.Token, agentID: archived})
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusForbidden || !strings.Contains(body, "AGENT_SUSPENDED") {
		t.Fatalf("status=%d body=%s", resp.StatusCode, body)
	}
	assertSecurityErrorEnvelope(t, resp, body, env.orgA.Token)
}

func TestSecurity_SEC2_7_ValidAgent(t *testing.T) {
	env := securityEnv(t)
	resp, _ := authProbeGET(t, orgAProbeOpts(env))
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("status=%d", resp.StatusCode)
	}
}
