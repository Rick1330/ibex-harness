//go:build integration

package proxy_test

import (
	"testing"
)

func TestSecurity_SEC6_1_JSONContentType(t *testing.T) {
	env := securityEnv(t)
	resp, body := authProbeGET(t, authProbeOpts{srvURL: env.proxy.URL, bearer: env.orgA.Token})
	defer resp.Body.Close()
	assertSecurityErrorEnvelope(t, resp, body, env.orgA.Token)
}

func TestSecurity_SEC6_2_ErrorSchema(t *testing.T) {
	env := securityEnv(t)
	resp, body := authProbeGET(t, authProbeOpts{srvURL: env.proxy.URL, bearer: "bad"})
	defer resp.Body.Close()
	assertSecurityErrorEnvelope(t, resp, body, "")
}

func TestSecurity_SEC6_3_RequestIDInBody(t *testing.T) {
	env := securityEnv(t)
	resp, body := authProbeGET(t, authProbeOpts{srvURL: env.proxy.URL, bearer: env.orgA.Token, agentID: "not-a-uuid"})
	defer resp.Body.Close()
	assertSecurityErrorEnvelope(t, resp, body, env.orgA.Token)
}

func TestSecurity_SEC6_4_RequestIDHeader(t *testing.T) {
	env := securityEnv(t)
	resp, body := authProbeGET(t, authProbeOpts{srvURL: env.proxy.URL})
	defer resp.Body.Close()
	if resp.Header.Get("X-Request-ID") == "" {
		t.Fatalf("missing X-Request-ID body=%s", body)
	}
	assertSecurityErrorEnvelope(t, resp, body, "")
}

func TestSecurity_SEC6_5_NoTokenLeak(t *testing.T) {
	env := securityEnv(t)
	cases := []authProbeOpts{
		{srvURL: env.proxy.URL, bearer: env.orgA.Token, agentID: env.orgB.AgentID},
		{srvURL: env.proxy.URL, bearer: env.orgA.Token},
		{srvURL: env.proxy.URL, bearer: "bad"},
	}
	for _, opts := range cases {
		resp, body := authProbeGET(t, opts)
		assertNoTokenLeak(t, body, opts.bearer)
		resp.Body.Close()
	}
}
