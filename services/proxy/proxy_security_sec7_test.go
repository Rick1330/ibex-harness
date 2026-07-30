//go:build integration

package proxy_test

import (
	"context"
	"net/http"
	"strings"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/infra/testing/testutil"
	apierror "github.com/Rick1330/ibex-harness/packages/apierror"
	"github.com/Rick1330/ibex-harness/packages/permissions"
	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/validation"
	"google.golang.org/grpc/metadata"
)

func TestSecurity_SEC7_1_ChatBodyTooLarge(t *testing.T) {
	env := securityEnv(t)
	chatToken, _ := testutil.SeedToken(t, env.db, env.orgA.OrgID, permissions.ProxyChatCompletion)
	oversized := strings.Repeat("x", int(validation.MaxRequestBodyBytes+1))

	resp, body := chatPOST(t, chatRequestOpts{
		srvURL: env.proxy.URL, bearer: chatToken, agentID: env.orgA.AgentID,
		contentType: "application/json", body: oversized,
	})
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusRequestEntityTooLarge {
		t.Fatalf("status=%d body=%s", resp.StatusCode, body)
	}
	requireErrorCode(t, body, apierror.CodePayloadTooLarge)
	assertSecurityErrorEnvelope(t, resp, body, chatToken)
}

func TestSecurity_SEC7_2_AuthCacheWarmThenRevoke(t *testing.T) {
	env := setupSecurityTestEnv(t, proxyServerOpts{defaultRPM: 60, withAuthCache: true})
	admin := testutil.SeedBootstrapAdminToken(t, env.db, env.orgA.OrgID)

	rpcCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	ctx := metadata.NewOutgoingContext(rpcCtx, metadata.Pairs("authorization", "Bearer "+admin))

	createResp, err := env.authFx.Client.CreateToken(ctx, &authv1.CreateTokenRequest{
		OrgId: env.orgA.OrgID, Name: "sec7-cache", Type: authv1.TokenType_TOKEN_TYPE_PAT, Permissions: 42,
	})
	if err != nil {
		t.Fatalf("create: %v", err)
	}
	plain := createResp.GetPlaintext()
	opts := authProbeOpts{srvURL: env.proxy.URL, bearer: plain, agentID: env.orgA.AgentID}

	// Miss then hit: second response must advertise cache via X-IBEX-Auth-Cached.
	requireProbeOKCached(t, opts, false)
	requireProbeOKCached(t, opts, true)

	start := time.Now()
	if _, err = env.authFx.Client.RevokeToken(ctx, &authv1.RevokeTokenRequest{
		OrgId: env.orgA.OrgID, TokenId: createResp.GetTokenId(),
	}); err != nil {
		t.Fatalf("revoke: %v", err)
	}
	env.authFx.WaitPendingPublishes()
	requireProbeUnauthorizedEventually(t, opts, plain, revocationSLA(t))
	if elapsed := time.Since(start); elapsed > revocationSLA(t) {
		t.Fatalf("revocation SLA exceeded: %v (limit %v)", elapsed, revocationSLA(t))
	}
}
