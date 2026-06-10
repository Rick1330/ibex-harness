//go:build integration

package proxy_test

import (
	"context"
	"net/http"
	"strings"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/infra/testing/testutil"
	"github.com/Rick1330/ibex-harness/packages/permissions"
	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"github.com/google/uuid"
	"google.golang.org/grpc/metadata"
)

func TestSecurityIntegrationSuite(t *testing.T) {
	env := setupSecurityTestEnv(t, proxyServerOpts{defaultRPM: 60})

	t.Run("SEC-1.1", func(t *testing.T) {
		resp, body := authProbeGET(t, authProbeOpts{srvURL: env.proxy.URL})
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusUnauthorized || !strings.Contains(body, "MISSING_TOKEN") {
			t.Fatalf("status=%d body=%s", resp.StatusCode, body)
		}
		assertSecurityErrorEnvelope(t, resp, body, "")
	})

	t.Run("SEC-1.2", func(t *testing.T) {
		req, _ := http.NewRequest(http.MethodGet, env.proxy.URL+"/v1/internal/auth-probe", nil)
		req.Header.Set("Authorization", "Bearer ")
		resp, err := http.DefaultClient.Do(req)
		if err != nil {
			t.Fatal(err)
		}
		body := readBody(resp)
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusUnauthorized {
			t.Fatalf("status=%d body=%s", resp.StatusCode, body)
		}
		assertSecurityErrorEnvelope(t, resp, body, "")
	})

	t.Run("SEC-1.3", func(t *testing.T) {
		resp, body := authProbeGET(t, authProbeOpts{srvURL: env.proxy.URL, bearer: "not_a_token"})
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusUnauthorized {
			t.Fatalf("status=%d body=%s", resp.StatusCode, body)
		}
		assertSecurityErrorEnvelope(t, resp, body, "not_a_token")
	})

	t.Run("SEC-1.4", func(t *testing.T) {
		resp, body := authProbeGET(t, authProbeOpts{
			srvURL: env.proxy.URL, bearer: "ibex_sk_unknowntoken", agentID: env.orgA.AgentID,
		})
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusUnauthorized {
			t.Fatalf("status=%d body=%s", resp.StatusCode, body)
		}
		assertSecurityErrorEnvelope(t, resp, body, "")
	})

	t.Run("SEC-1.5", func(t *testing.T) {
		admin := testutil.SeedBootstrapAdminToken(t, env.db, env.orgA.OrgID)
		createCtx := metadata.NewOutgoingContext(context.Background(), metadata.Pairs("authorization", "Bearer "+admin))
		createResp, err := env.authFx.Client.CreateToken(createCtx, &authv1.CreateTokenRequest{
			OrgId: env.orgA.OrgID, Name: "revoke-sec", Type: authv1.TokenType_TOKEN_TYPE_PAT, Permissions: 42,
		})
		if err != nil {
			t.Fatalf("create: %v", err)
		}
		plain := createResp.GetPlaintext()
		resp, _ := authProbeGET(t, authProbeOpts{srvURL: env.proxy.URL, bearer: plain, agentID: env.orgA.AgentID})
		resp.Body.Close()
		if resp.StatusCode != http.StatusOK {
			t.Fatalf("pre-revoke status=%d", resp.StatusCode)
		}
		start := time.Now()
		_, err = env.authFx.Client.RevokeToken(createCtx, &authv1.RevokeTokenRequest{
			OrgId: env.orgA.OrgID, TokenId: createResp.GetTokenId(),
		})
		if err != nil {
			t.Fatalf("revoke: %v", err)
		}
		resp2, body := authProbeGET(t, authProbeOpts{srvURL: env.proxy.URL, bearer: plain, agentID: env.orgA.AgentID})
		defer resp2.Body.Close()
		elapsed := time.Since(start)
		if resp2.StatusCode != http.StatusUnauthorized {
			t.Fatalf("post-revoke status=%d body=%s", resp2.StatusCode, body)
		}
		if elapsed > 100*time.Millisecond {
			t.Fatalf("revocation SLA exceeded: %v", elapsed)
		}
		assertSecurityErrorEnvelope(t, resp2, body, plain)
	})

	t.Run("SEC-1.6", func(t *testing.T) {
		expired := testutil.SeedTokenExpired(t, env.db, env.orgA.OrgID, 42)
		resp, body := authProbeGET(t, authProbeOpts{srvURL: env.proxy.URL, bearer: expired, agentID: env.orgA.AgentID})
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusUnauthorized || !strings.Contains(body, "INVALID_TOKEN") {
			t.Fatalf("status=%d body=%s", resp.StatusCode, body)
		}
		assertSecurityErrorEnvelope(t, resp, body, expired)
	})

	t.Run("SEC-1.7", func(t *testing.T) {
		resp, _ := authProbeGET(t, authProbeOpts{srvURL: env.proxy.URL, bearer: env.orgA.Token, agentID: env.orgA.AgentID})
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusOK {
			t.Fatalf("status=%d", resp.StatusCode)
		}
	})

	t.Run("SEC-2.1", func(t *testing.T) {
		resp, body := authProbeGET(t, authProbeOpts{srvURL: env.proxy.URL, bearer: env.orgA.Token})
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusBadRequest || !strings.Contains(body, "MISSING_AGENT_ID") {
			t.Fatalf("status=%d body=%s", resp.StatusCode, body)
		}
		assertSecurityErrorEnvelope(t, resp, body, env.orgA.Token)
	})

	t.Run("SEC-2.2", func(t *testing.T) {
		resp, body := authProbeGET(t, authProbeOpts{srvURL: env.proxy.URL, bearer: env.orgA.Token, agentID: "not-a-uuid"})
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusBadRequest || !strings.Contains(body, "VALIDATION_ERROR") {
			t.Fatalf("status=%d body=%s", resp.StatusCode, body)
		}
		assertSecurityErrorEnvelope(t, resp, body, env.orgA.Token)
	})

	t.Run("SEC-2.3", func(t *testing.T) {
		unknown := uuid.New().String()
		resp, body := authProbeGET(t, authProbeOpts{srvURL: env.proxy.URL, bearer: env.orgA.Token, agentID: unknown})
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusForbidden || !strings.Contains(body, "AGENT_NOT_AUTHORIZED") {
			t.Fatalf("status=%d body=%s", resp.StatusCode, body)
		}
		assertSecurityErrorEnvelope(t, resp, body, env.orgA.Token)
	})

	t.Run("SEC-2.4", func(t *testing.T) {
		resp, body := authProbeGET(t, authProbeOpts{srvURL: env.proxy.URL, bearer: env.orgA.Token, agentID: env.orgB.AgentID})
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusForbidden || !strings.Contains(body, "AGENT_NOT_AUTHORIZED") {
			t.Fatalf("status=%d body=%s", resp.StatusCode, body)
		}
		assertSecurityErrorEnvelope(t, resp, body, env.orgA.Token)
	})

	t.Run("SEC-2.5", func(t *testing.T) {
		paused := testutil.SeedAgentWithStatus(t, env.db, env.orgA.OrgID, env.orgA.UserID, "Paused", "paused-"+uuid.NewString()[:8], "paused")
		resp, body := authProbeGET(t, authProbeOpts{srvURL: env.proxy.URL, bearer: env.orgA.Token, agentID: paused})
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusForbidden || !strings.Contains(body, "AGENT_SUSPENDED") {
			t.Fatalf("status=%d body=%s", resp.StatusCode, body)
		}
		assertSecurityErrorEnvelope(t, resp, body, env.orgA.Token)
	})

	t.Run("SEC-2.6", func(t *testing.T) {
		archived := testutil.SeedAgentWithStatus(t, env.db, env.orgA.OrgID, env.orgA.UserID, "Archived", "archived-"+uuid.NewString()[:8], "archived")
		resp, body := authProbeGET(t, authProbeOpts{srvURL: env.proxy.URL, bearer: env.orgA.Token, agentID: archived})
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusForbidden || !strings.Contains(body, "AGENT_SUSPENDED") {
			t.Fatalf("status=%d body=%s", resp.StatusCode, body)
		}
		assertSecurityErrorEnvelope(t, resp, body, env.orgA.Token)
	})

	t.Run("SEC-2.7", func(t *testing.T) {
		resp, _ := authProbeGET(t, authProbeOpts{srvURL: env.proxy.URL, bearer: env.orgA.Token, agentID: env.orgA.AgentID})
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusOK {
			t.Fatalf("status=%d", resp.StatusCode)
		}
	})

	t.Run("SEC-3.1", func(t *testing.T) {
		resp, _ := authProbeGET(t, authProbeOpts{srvURL: env.proxy.URL, bearer: env.orgA.Token, agentID: env.orgA.AgentID})
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusOK {
			t.Fatalf("status=%d", resp.StatusCode)
		}
	})

	t.Run("SEC-3.2", func(t *testing.T) {
		resp, body := authProbeGET(t, authProbeOpts{srvURL: env.proxy.URL, bearer: env.orgA.Token, agentID: env.orgB.AgentID})
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusForbidden {
			t.Fatalf("status=%d want 403 not 404 body=%s", resp.StatusCode, body)
		}
		assertSecurityErrorEnvelope(t, resp, body, env.orgA.Token)
	})

	t.Run("SEC-3.3", func(t *testing.T) {
		resp, body := authProbeGET(t, authProbeOpts{srvURL: env.proxy.URL, bearer: env.orgB.Token, agentID: env.orgA.AgentID})
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusForbidden {
			t.Fatalf("status=%d want 403 not 404 body=%s", resp.StatusCode, body)
		}
		assertSecurityErrorEnvelope(t, resp, body, env.orgB.Token)
	})

	t.Run("SEC-3.4", func(t *testing.T) {
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
		p95A := percentileMs(latA, 0.95)
		p95B := percentileMs(latB, 0.95)
		delta := p95A - p95B
		if delta < 0 {
			delta = -delta
		}
		if delta > 25*time.Millisecond {
			t.Fatalf("timing delta p95=%v exceeds 25ms (A=%v B=%v)", delta, p95A, p95B)
		}
	})

	t.Run("SEC-5.1", func(t *testing.T) {
		zero := testutil.SeedTokenZeroPerms(t, env.db, env.orgA.OrgID)
		resp, body := chatPOST(t, chatRequestOpts{
			srvURL: env.proxy.URL, bearer: zero, agentID: env.orgA.AgentID,
			contentType: "application/json", body: minimalChatBody,
		})
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusForbidden || !strings.Contains(body, "INSUFFICIENT_PERMISSIONS") {
			t.Fatalf("status=%d body=%s", resp.StatusCode, body)
		}
		assertSecurityErrorEnvelope(t, resp, body, zero)
	})

	t.Run("SEC-5.2", func(t *testing.T) {
		readOnly, _ := testutil.SeedToken(t, env.db, env.orgA.OrgID, permissions.ReadOnly)
		resp, body := chatPOST(t, chatRequestOpts{
			srvURL: env.proxy.URL, bearer: readOnly, agentID: env.orgA.AgentID,
			contentType: "application/json", body: minimalChatBody,
		})
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusForbidden || !strings.Contains(body, "INSUFFICIENT_PERMISSIONS") {
			t.Fatalf("status=%d body=%s", resp.StatusCode, body)
		}
		assertSecurityErrorEnvelope(t, resp, body, readOnly)
	})

	t.Run("SEC-5.3", func(t *testing.T) {
		chatToken, _ := testutil.SeedToken(t, env.db, env.orgA.OrgID, permissions.ProxyChatCompletion)
		resp, body := chatPOST(t, chatRequestOpts{
			srvURL: env.proxy.URL, bearer: chatToken, agentID: env.orgA.AgentID,
			contentType: "application/json", body: minimalChatBody,
		})
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusNotImplemented || !strings.Contains(body, "PROVIDER_NOT_CONFIGURED") {
			t.Fatalf("status=%d body=%s", resp.StatusCode, body)
		}
		assertSecurityErrorEnvelope(t, resp, body, chatToken)
	})

	t.Run("SEC-6.1", func(t *testing.T) {
		resp, body := authProbeGET(t, authProbeOpts{srvURL: env.proxy.URL, bearer: env.orgA.Token})
		defer resp.Body.Close()
		assertSecurityErrorEnvelope(t, resp, body, env.orgA.Token)
	})

	t.Run("SEC-6.2", func(t *testing.T) {
		resp, body := authProbeGET(t, authProbeOpts{srvURL: env.proxy.URL, bearer: "bad"})
		defer resp.Body.Close()
		assertSecurityErrorEnvelope(t, resp, body, "")
	})

	t.Run("SEC-6.3", func(t *testing.T) {
		resp, body := authProbeGET(t, authProbeOpts{srvURL: env.proxy.URL, bearer: env.orgA.Token, agentID: "not-a-uuid"})
		defer resp.Body.Close()
		assertSecurityErrorEnvelope(t, resp, body, env.orgA.Token)
	})

	t.Run("SEC-6.4", func(t *testing.T) {
		resp, body := authProbeGET(t, authProbeOpts{srvURL: env.proxy.URL})
		defer resp.Body.Close()
		if resp.Header.Get("X-Request-ID") == "" {
			t.Fatalf("missing X-Request-ID body=%s", body)
		}
		assertSecurityErrorEnvelope(t, resp, body, "")
	})

	t.Run("SEC-6.5", func(t *testing.T) {
		cases := []struct {
			bearer  string
			agentID string
		}{
			{bearer: env.orgA.Token, agentID: env.orgB.AgentID},
			{bearer: env.orgA.Token},
			{bearer: "bad"},
		}
		for _, tc := range cases {
			resp, body := authProbeGET(t, authProbeOpts{srvURL: env.proxy.URL, bearer: tc.bearer, agentID: tc.agentID})
			assertNoTokenLeak(t, body, tc.bearer)
			resp.Body.Close()
		}
	})
}

// rateLimitBurstRPM is low so 429 is reached within one calendar minute (avoids window rollover flakes).
const rateLimitBurstRPM int64 = 5

func TestSecurityIntegrationRateLimit(t *testing.T) {
	t.Run("SEC-4.1", func(t *testing.T) {
		env := setupSecurityTestEnv(t, proxyServerOpts{defaultRPM: rateLimitBurstRPM})
		prevRemaining := -1
		for i := 0; i < 3; i++ {
			resp, _ := authProbeGET(t, authProbeOpts{
				srvURL: env.proxy.URL, bearer: env.orgA.Token, agentID: env.orgA.AgentID,
			})
			rem := parseIntHeader(t, resp.Header.Get("X-RateLimit-Remaining"))
			resp.Body.Close()
			if prevRemaining >= 0 && rem >= prevRemaining {
				t.Fatalf("remaining did not decrement: prev=%d cur=%d", prevRemaining, rem)
			}
			prevRemaining = rem
		}
	})

	t.Run("SEC-4.2", func(t *testing.T) {
		env := setupSecurityTestEnv(t, proxyServerOpts{defaultRPM: rateLimitBurstRPM})
		var lastResp *http.Response
		var lastBody string
		burst := int(rateLimitBurstRPM) + 1
		for i := 0; i < burst; i++ {
			resp, body := authProbeGET(t, authProbeOpts{
				srvURL: env.proxy.URL, bearer: env.orgA.Token, agentID: env.orgA.AgentID,
			})
			lastResp = resp
			lastBody = body
		}
		defer lastResp.Body.Close()
		if lastResp.StatusCode != http.StatusTooManyRequests || !strings.Contains(lastBody, "RATE_LIMITED") {
			t.Fatalf("burst request status=%d body=%s", lastResp.StatusCode, lastBody)
		}
		assertSecurityErrorEnvelope(t, lastResp, lastBody, env.orgA.Token)
	})

	t.Run("SEC-4.3", func(t *testing.T) {
		env := setupSecurityTestEnv(t, proxyServerOpts{defaultRPM: rateLimitBurstRPM})
		burst := int(rateLimitBurstRPM) + 1
		for i := 0; i < burst; i++ {
			resp, _ := authProbeGET(t, authProbeOpts{
				srvURL: env.proxy.URL, bearer: env.orgA.Token, agentID: env.orgA.AgentID,
			})
			if resp.StatusCode == http.StatusTooManyRequests {
				ra := parseRetryAfter(t, resp.Header.Get("Retry-After"))
				if ra <= 0 || ra > 60 {
					t.Fatalf("Retry-After out of range: %d", ra)
				}
				resp.Body.Close()
				return
			}
			resp.Body.Close()
		}
		t.Fatal("never received 429")
	})

	t.Run("SEC-4.4", func(t *testing.T) {
		env := setupSecurityTestEnv(t, proxyServerOpts{defaultRPM: rateLimitBurstRPM})
		burst := int(rateLimitBurstRPM) + 1
		for i := 0; i < burst; i++ {
			resp, _ := authProbeGET(t, authProbeOpts{
				srvURL: env.proxy.URL, bearer: env.orgA.Token, agentID: env.orgA.AgentID,
			})
			if resp.StatusCode == http.StatusTooManyRequests {
				reset := parseResetUnix(t, resp.Header.Get("X-RateLimit-Reset"))
				now := time.Now().Unix()
				if reset < now || reset > now+60 {
					t.Fatalf("X-RateLimit-Reset out of range: reset=%d now=%d", reset, now)
				}
				resp.Body.Close()
				return
			}
			resp.Body.Close()
		}
		t.Fatal("never received 429")
	})

	t.Run("SEC-4.5", func(t *testing.T) {
		env := setupSecurityTestEnv(t, proxyServerOpts{defaultRPM: rateLimitBurstRPM})
		burst := int(rateLimitBurstRPM) + 1
		for i := 0; i < burst; i++ {
			resp, _ := authProbeGET(t, authProbeOpts{
				srvURL: env.proxy.URL, bearer: env.orgA.Token, agentID: env.orgA.AgentID,
			})
			resp.Body.Close()
		}
		resp, _ := authProbeGET(t, authProbeOpts{
			srvURL: env.proxy.URL, bearer: env.orgB.Token, agentID: env.orgB.AgentID,
		})
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusOK {
			t.Fatalf("org B status=%d after org A exhaustion", resp.StatusCode)
		}
	})
}
