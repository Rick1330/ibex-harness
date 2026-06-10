//go:build integration

package proxy_test

import (
	"net/http"
	"testing"
	"time"
)

func TestSecurity_SEC3_1_SameOrgAllowed(t *testing.T) {
	env := securityEnv(t)
	resp, _ := authProbeGET(t, orgAProbeOpts(env))
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("status=%d", resp.StatusCode)
	}
}

func TestSecurity_SEC3_2_CrossOrgRejected(t *testing.T) {
	env := securityEnv(t)
	resp, body := authProbeGET(t, authProbeOpts{srvURL: env.proxy.URL, bearer: env.orgA.Token, agentID: env.orgB.AgentID})
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusForbidden {
		t.Fatalf("status=%d want 403 body=%s", resp.StatusCode, body)
	}
	assertSecurityErrorEnvelope(t, resp, body, env.orgA.Token)
}

func TestSecurity_SEC3_3_ReverseCrossOrgRejected(t *testing.T) {
	env := securityEnv(t)
	resp, body := authProbeGET(t, authProbeOpts{srvURL: env.proxy.URL, bearer: env.orgB.Token, agentID: env.orgA.AgentID})
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusForbidden {
		t.Fatalf("status=%d want 403 body=%s", resp.StatusCode, body)
	}
	assertSecurityErrorEnvelope(t, resp, body, env.orgB.Token)
}

func TestSecurity_SEC3_4_TimingParity(t *testing.T) {
	env := securityEnv(t)
	const samples = 50
	var latA, latB []time.Duration
	for i := 0; i < samples; i++ {
		start := time.Now()
		resp, _ := authProbeGET(t, authProbeOpts{srvURL: env.proxy.URL, bearer: env.orgA.Token, agentID: env.orgB.AgentID})
		latA = append(latA, time.Since(start))
		resp.Body.Close()

		start = time.Now()
		resp2, _ := authProbeGET(t, authProbeOpts{srvURL: env.proxy.URL, bearer: env.orgB.Token, agentID: env.orgA.AgentID})
		latB = append(latB, time.Since(start))
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
