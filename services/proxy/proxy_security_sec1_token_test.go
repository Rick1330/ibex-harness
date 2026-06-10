//go:build integration

package proxy_test

import (
	"context"
	"net/http"
	"strings"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/infra/testing/testutil"
	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"google.golang.org/grpc/metadata"
)

func TestSecurity_SEC1_1_MissingToken(t *testing.T) {
	env := securityEnv(t)
	resp, body := authProbeGET(t, authProbeOpts{srvURL: env.proxy.URL})
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusUnauthorized || !strings.Contains(body, "MISSING_TOKEN") {
		t.Fatalf("status=%d body=%s", resp.StatusCode, body)
	}
	assertSecurityErrorEnvelope(t, resp, body, "")
}

func TestSecurity_SEC1_2_EmptyBearer(t *testing.T) {
	env := securityEnv(t)
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
}

func TestSecurity_SEC1_3_MalformedToken(t *testing.T) {
	env := securityEnv(t)
	resp, body := authProbeGET(t, authProbeOpts{srvURL: env.proxy.URL, bearer: "not_a_token"})
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusUnauthorized {
		t.Fatalf("status=%d body=%s", resp.StatusCode, body)
	}
	assertSecurityErrorEnvelope(t, resp, body, "not_a_token")
}

func TestSecurity_SEC1_4_UnknownToken(t *testing.T) {
	env := securityEnv(t)
	resp, body := authProbeGET(t, authProbeOpts{
		srvURL: env.proxy.URL, bearer: "ibex_sk_unknowntoken", agentID: env.orgA.AgentID,
	})
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusUnauthorized {
		t.Fatalf("status=%d body=%s", resp.StatusCode, body)
	}
	assertSecurityErrorEnvelope(t, resp, body, "")
}

func TestSecurity_SEC1_5_RevokedTokenSLA(t *testing.T) {
	env := securityEnv(t)
	admin := testutil.SeedBootstrapAdminToken(t, env.db, env.orgA.OrgID)
	ctx := metadata.NewOutgoingContext(context.Background(), metadata.Pairs("authorization", "Bearer "+admin))
	createResp, err := env.authFx.Client.CreateToken(ctx, &authv1.CreateTokenRequest{
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
	if _, err = env.authFx.Client.RevokeToken(ctx, &authv1.RevokeTokenRequest{
		OrgId: env.orgA.OrgID, TokenId: createResp.GetTokenId(),
	}); err != nil {
		t.Fatalf("revoke: %v", err)
	}
	resp2, body := authProbeGET(t, authProbeOpts{srvURL: env.proxy.URL, bearer: plain, agentID: env.orgA.AgentID})
	defer resp2.Body.Close()
	if resp2.StatusCode != http.StatusUnauthorized || time.Since(start) > 100*time.Millisecond {
		t.Fatalf("post-revoke status=%d elapsed=%v body=%s", resp2.StatusCode, time.Since(start), body)
	}
	assertSecurityErrorEnvelope(t, resp2, body, plain)
}

func TestSecurity_SEC1_6_ExpiredToken(t *testing.T) {
	env := securityEnv(t)
	expired := testutil.SeedTokenExpired(t, env.db, env.orgA.OrgID, 42)
	resp, body := authProbeGET(t, authProbeOpts{srvURL: env.proxy.URL, bearer: expired, agentID: env.orgA.AgentID})
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusUnauthorized || !strings.Contains(body, "INVALID_TOKEN") {
		t.Fatalf("status=%d body=%s", resp.StatusCode, body)
	}
	assertSecurityErrorEnvelope(t, resp, body, expired)
}

func TestSecurity_SEC1_7_ValidToken(t *testing.T) {
	env := securityEnv(t)
	resp, _ := authProbeGET(t, orgAProbeOpts(env))
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("status=%d", resp.StatusCode)
	}
}
