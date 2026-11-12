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

// P0-21's remaining half: the chat path had no two-tenant negative.
// SEC3.2/SEC3.3 prove the agent/org binding through the test-only
// /v1/internal/auth-probe handler; these tests drive a real chat completion
// through the protected router so the assertion covers the shipping chain —
// BodySizeLimit → ContentType → Auth → AgentVerification → … → provider.
//
// The provider counter is the load-bearing assertion: a 403 alone would still
// pass if the handler had already reached the provider and then failed to
// write a response, which is exactly the cross-tenant read this test exists to
// exclude.

type chatTenancyEnv struct {
	env      securityTestEnv
	chatA    string
	chatB    string
	provider *outageCountingProvider
}

func newChatTenancyEnv(t *testing.T) chatTenancyEnv {
	t.Helper()
	// outageCountingProvider is the package's existing counting forwarder.
	counter := &outageCountingProvider{}
	env := setupSecurityTestEnv(t, proxyServerOpts{
		defaultRPM: 60,
		providers:  []provider.Provider{counter},
	})
	// The fixture tokens carry bitmap 42, which does not satisfy
	// RequireProxyChatCompletion; seed the minimum chat set per org with the
	// same helper SEC4.7 and SEC5 use.
	chatA, _ := testutil.SeedToken(t, env.db, env.orgA.OrgID, permissions.ProxyChatCompletion)
	chatB, _ := testutil.SeedToken(t, env.db, env.orgB.OrgID, permissions.ProxyChatCompletion)
	return chatTenancyEnv{env: env, chatA: chatA, chatB: chatB, provider: counter}
}

func (e chatTenancyEnv) postChat(t *testing.T, bearer, agentID string) (*http.Response, string) {
	t.Helper()
	return chatPOST(t, chatRequestOpts{
		srvURL: e.env.proxy.URL, bearer: bearer, agentID: agentID,
		contentType: "application/json", body: minimalChatBody,
	})
}

func TestSecurity_P021_ChatCrossOrgAgentRejected(t *testing.T) {
	e := newChatTenancyEnv(t)

	cases := []struct {
		name       string
		bearer     string
		agentID    string
		foreignOrg string
	}{
		{
			name: "orgA_token_naming_orgB_agent", bearer: e.chatA,
			agentID: e.env.orgB.AgentID, foreignOrg: e.env.orgB.OrgID,
		},
		{
			name: "orgB_token_naming_orgA_agent", bearer: e.chatB,
			agentID: e.env.orgA.AgentID, foreignOrg: e.env.orgA.OrgID,
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			before := e.provider.calls.Load()
			resp, body := e.postChat(t, tc.bearer, tc.agentID)
			defer func() { _ = resp.Body.Close() }()

			if resp.StatusCode != http.StatusForbidden {
				t.Fatalf("status=%d want=%d body=%s", resp.StatusCode, http.StatusForbidden, body)
			}
			requireErrorCode(t, body, apierror.CodeAgentNotAuthorized)
			assertSecurityErrorEnvelope(t, resp, body, tc.bearer)

			if got := e.provider.calls.Load(); got != before {
				t.Fatalf("provider calls=%d want=%d: cross-org chat reached the provider", got, before)
			}
			for _, identifier := range []string{tc.agentID, tc.foreignOrg} {
				if strings.Contains(body, identifier) {
					t.Fatalf("response body leaks foreign-tenant identifier %q: %s", identifier, body)
				}
			}
		})
	}

	if got := e.provider.calls.Load(); got != 0 {
		t.Fatalf("provider calls=%d after both denied arms; want 0", got)
	}
}

// TestSecurity_P021_ChatSameOrgAgentReachesProvider is the positive control:
// without it a harness that never reaches the provider would make both
// negatives pass vacuously.
func TestSecurity_P021_ChatSameOrgAgentReachesProvider(t *testing.T) {
	e := newChatTenancyEnv(t)

	resp, body := e.postChat(t, e.chatA, e.env.orgA.AgentID)
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode != http.StatusOK {
		t.Fatalf("status=%d want=200 body=%s", resp.StatusCode, body)
	}
	if got := e.provider.calls.Load(); got != 1 {
		t.Fatalf("provider calls=%d want=1 after one allowed chat completion", got)
	}
	if !strings.Contains(body, "assistant") {
		t.Fatalf("body=%s", body)
	}
	if strings.Contains(body, e.env.orgB.AgentID) || strings.Contains(body, e.env.orgB.OrgID) {
		t.Fatalf("same-org response carries foreign-tenant identifiers: %s", body)
	}
}
