//go:build integration

package proxy_test

import (
	"net/http"
	"testing"
	"time"

	apierror "github.com/Rick1330/ibex-harness/packages/apierror"
)

func TestSecurity_SEC3_1_SameOrgAllowed(t *testing.T) {
	env := securityEnv(t)
	requireProbeOK(t, orgAProbeOpts(env))
}

func TestSecurity_SEC3_2_CrossOrgRejected(t *testing.T) {
	env := securityEnv(t)
	requireProbe(t, authProbeOpts{srvURL: env.proxy.URL, bearer: env.orgA.Token, agentID: env.orgB.AgentID},
		probeExpect{http.StatusForbidden, apierror.CodeAgentNotAuthorized}, env.orgA.Token)
}

func TestSecurity_SEC3_3_ReverseCrossOrgRejected(t *testing.T) {
	env := securityEnv(t)
	requireProbe(t, authProbeOpts{srvURL: env.proxy.URL, bearer: env.orgB.Token, agentID: env.orgA.AgentID},
		probeExpect{http.StatusForbidden, apierror.CodeAgentNotAuthorized}, env.orgB.Token)
}

func TestSecurity_SEC3_4_TimingParity(t *testing.T) {
	env := securityEnv(t)
	const samples = 50
	var latA, latB []time.Duration
	for i := 0; i < samples; i++ {
		start := time.Now()
		resp, body := authProbeGET(t, authProbeOpts{srvURL: env.proxy.URL, bearer: env.orgA.Token, agentID: env.orgB.AgentID})
		latA = append(latA, time.Since(start))
		if resp.StatusCode != http.StatusForbidden {
			t.Fatalf("SEC3.2 arm status=%d body=%s", resp.StatusCode, body)
		}
		resp.Body.Close()

		start = time.Now()
		resp2, body2 := authProbeGET(t, authProbeOpts{srvURL: env.proxy.URL, bearer: env.orgB.Token, agentID: env.orgA.AgentID})
		latB = append(latB, time.Since(start))
		if resp2.StatusCode != http.StatusForbidden {
			t.Fatalf("SEC3.3 arm status=%d body=%s", resp2.StatusCode, body2)
		}
		resp2.Body.Close()
	}
	delta := percentileMs(latA, 0.95) - percentileMs(latB, 0.95)
	if delta < 0 {
		delta = -delta
	}
	if delta > timingParityThresholdMs*time.Millisecond {
		t.Fatalf("timing delta p95=%v exceeds %dms", delta, timingParityThresholdMs)
	}
}

func TestSecurity_SEC3_5_PathOrgMismatch(t *testing.T) {
	env := securityEnv(t)
	resp, body := orgAuthProbeGET(t, orgAuthProbeOpts{
		srvURL: env.proxy.URL, orgID: env.orgB.OrgID, bearer: env.orgA.Token, agentID: env.orgA.AgentID,
	})
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusForbidden {
		t.Fatalf("status=%d body=%s", resp.StatusCode, body)
	}
	requireErrorCode(t, body, apierror.CodeInsufficientPermissions)
	assertSecurityErrorEnvelope(t, resp, body, env.orgA.Token)
}
