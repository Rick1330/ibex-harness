//go:build integration

package proxy_test

import (
	"net/http"
	"testing"

	"github.com/Rick1330/ibex-harness/infra/testing/testutil"
	"github.com/Rick1330/ibex-harness/packages/permissions"
)

func TestSecurity_SEC6_EnvelopeSweep(t *testing.T) {
	env := securityEnv(t)
	chatToken, _ := testutil.SeedToken(t, env.db, env.orgA.OrgID, permissions.ProxyChatCompletion)

	cases := []struct {
		name   string
		run    func() (*http.Response, string)
		secret string
	}{
		{
			name: "401_missing_token",
			run: func() (*http.Response, string) {
				return authProbeGET(t, authProbeOpts{srvURL: env.proxy.URL})
			},
		},
		{
			name: "400_missing_agent",
			run: func() (*http.Response, string) {
				return authProbeGET(t, authProbeOpts{srvURL: env.proxy.URL, bearer: env.orgA.Token})
			},
			secret: env.orgA.Token,
		},
		{
			name: "403_cross_org_agent",
			run: func() (*http.Response, string) {
				return authProbeGET(t, authProbeOpts{srvURL: env.proxy.URL, bearer: env.orgA.Token, agentID: env.orgB.AgentID})
			},
			secret: env.orgA.Token,
		},
		{
			name: "403_path_org_mismatch",
			run: func() (*http.Response, string) {
				return orgAuthProbeGET(t, orgAuthProbeOpts{
					srvURL: env.proxy.URL, orgID: env.orgB.OrgID, bearer: env.orgA.Token, agentID: env.orgA.AgentID,
				})
			},
			secret: env.orgA.Token,
		},
		{
			name: "429_rate_limited",
			run: func() (*http.Response, string) {
				rateEnv := rateLimitEnv(t)
				resp, body := requireRateLimitedProbe(t, rateEnv)
				return resp, body
			},
			secret: env.orgA.Token,
		},
		{
			name: "501_provider_not_configured",
			run: func() (*http.Response, string) {
				return chatPOST(t, chatRequestOpts{
					srvURL: env.proxy.URL, bearer: chatToken, agentID: env.orgA.AgentID,
					contentType: "application/json", body: minimalChatBody,
				})
			},
			secret: chatToken,
		},
		{
			name: "503_auth_unavailable",
			run: func() (*http.Response, string) {
				down := securityEnv(t)
				down.authFx.Close()
				return authProbeGET(t, orgAProbeOpts(down))
			},
			secret: env.orgA.Token,
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			resp, body := tc.run()
			defer resp.Body.Close()
			if resp.StatusCode < 400 {
				t.Fatalf("status=%d want error body=%s", resp.StatusCode, body)
			}
			assertSecurityErrorEnvelope(t, resp, body, tc.secret)
		})
	}
}

func TestSecurity_SEC6_5_NoTokenLeak(t *testing.T) {
	env := securityEnv(t)
	// Use a long sentinel so short substrings (e.g. "bad") cannot false-positive
	// against unrelated response text.
	const leakSentinel = "ibex_pat_leak-check-sentinel-9f3c2a1b0e8d"
	cases := []struct {
		name string
		opts authProbeOpts
	}{
		{
			name: "cross_org_agent",
			opts: authProbeOpts{srvURL: env.proxy.URL, bearer: env.orgA.Token, agentID: env.orgB.AgentID},
		},
		{
			name: "missing_agent",
			opts: authProbeOpts{srvURL: env.proxy.URL, bearer: env.orgA.Token},
		},
		{
			name: "unknown_token",
			opts: authProbeOpts{srvURL: env.proxy.URL, bearer: leakSentinel},
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			resp, body := authProbeGET(t, tc.opts)
			defer resp.Body.Close()
			assertNoTokenLeak(t, body, tc.opts.bearer)
		})
	}
}
