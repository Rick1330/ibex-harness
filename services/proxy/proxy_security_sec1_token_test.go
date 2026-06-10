//go:build integration

package proxy_test

import (
	"context"
	"net/http"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/infra/testing/testutil"
	apierror "github.com/Rick1330/ibex-harness/packages/apierror"
	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"google.golang.org/grpc/metadata"
)

func TestSecurity_SEC1_1_MissingToken(t *testing.T) {
	env := securityEnv(t)
	requireProbe(t, authProbeOpts{srvURL: env.proxy.URL}, probeExpect{http.StatusUnauthorized, apierror.CodeMissingToken}, "")
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
	requireErrorCode(t, body, apierror.CodeMissingToken)
	assertSecurityErrorEnvelope(t, resp, body, "")
}

func TestSecurity_SEC1_3_and_4_InvalidTokens(t *testing.T) {
	env := securityEnv(t)
	cases := []struct {
		name   string
		bearer string
		agent  string
		secret string
	}{
		{"SEC1_3_MalformedToken", "not_a_token", "", "not_a_token"},
		{"SEC1_4_UnknownToken", "ibex_sk_unknowntoken", env.orgA.AgentID, ""},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			requireProbe(t, authProbeOpts{srvURL: env.proxy.URL, bearer: tc.bearer, agentID: tc.agent},
				probeExpect{http.StatusUnauthorized, apierror.CodeInvalidToken}, tc.secret)
		})
	}
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
	requireProbeOK(t, authProbeOpts{srvURL: env.proxy.URL, bearer: plain, agentID: env.orgA.AgentID})
	start := time.Now()
	if _, err = env.authFx.Client.RevokeToken(ctx, &authv1.RevokeTokenRequest{
		OrgId: env.orgA.OrgID, TokenId: createResp.GetTokenId(),
	}); err != nil {
		t.Fatalf("revoke: %v", err)
	}
	requireProbe(t, authProbeOpts{srvURL: env.proxy.URL, bearer: plain, agentID: env.orgA.AgentID},
		probeExpect{http.StatusUnauthorized, apierror.CodeInvalidToken}, plain)
	if elapsed := time.Since(start); elapsed > revocationSLA(t) {
		t.Fatalf("revocation SLA exceeded: %v (limit %v)", elapsed, revocationSLA(t))
	}
}

func TestSecurity_SEC1_6_ExpiredToken(t *testing.T) {
	env := securityEnv(t)
	expired := testutil.SeedTokenExpired(t, env.db, env.orgA.OrgID, 42)
	requireProbe(t, authProbeOpts{srvURL: env.proxy.URL, bearer: expired, agentID: env.orgA.AgentID},
		probeExpect{http.StatusUnauthorized, apierror.CodeInvalidToken}, expired)
}

func TestSecurity_SEC1_7_ValidToken(t *testing.T) {
	env := securityEnv(t)
	requireProbeOK(t, orgAProbeOpts(env))
}
