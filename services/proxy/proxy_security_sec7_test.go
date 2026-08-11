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

type sec7TokenProbe struct {
	env     securityTestEnv
	authMD  metadata.MD
	tokenID string
	opts    authProbeOpts
	plain   string
}

// newSec7TokenProbe creates a PAT via auth gRPC and returns probe opts for the proxy.
func newSec7TokenProbe(t *testing.T, env securityTestEnv, tokenName string) sec7TokenProbe {
	t.Helper()
	admin := testutil.SeedBootstrapAdminToken(t, env.db, env.orgA.OrgID)
	authMD := metadata.Pairs("authorization", "Bearer "+admin)
	rpcCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	ctx := metadata.NewOutgoingContext(rpcCtx, authMD)

	createResp, err := env.authFx.Client.CreateToken(ctx, &authv1.CreateTokenRequest{
		OrgId: env.orgA.OrgID, Name: tokenName, Type: authv1.TokenType_TOKEN_TYPE_PAT,
		Permissions: permissions.ProxyChatCompletion,
	})
	if err != nil {
		t.Fatalf("create: %v", err)
	}
	plain := createResp.GetPlaintext()
	return sec7TokenProbe{
		env:     env,
		authMD:  authMD,
		tokenID: createResp.GetTokenId(),
		plain:   plain,
		opts:    authProbeOpts{srvURL: env.proxy.URL, bearer: plain, agentID: env.orgA.AgentID},
	}
}

func (p sec7TokenProbe) revoke(t *testing.T) {
	t.Helper()
	rpcCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	ctx := metadata.NewOutgoingContext(rpcCtx, p.authMD)
	if _, err := p.env.authFx.Client.RevokeToken(ctx, &authv1.RevokeTokenRequest{
		OrgId: p.env.orgA.OrgID, TokenId: p.tokenID,
	}); err != nil {
		t.Fatalf("revoke: %v", err)
	}
}

func TestSecurity_SEC7_2_AuthCacheWarmThenRevoke(t *testing.T) {
	env := setupSecurityTestEnv(t, proxyServerOpts{defaultRPM: 60, withAuthCache: true})
	p := newSec7TokenProbe(t, env, "sec7-cache")

	// Miss then hit: second response must advertise cache via X-IBEX-Auth-Cached.
	requireProbeOKCached(t, p.opts, false)
	requireProbeOKCached(t, p.opts, true)

	start := time.Now()
	p.revoke(t)
	env.authFx.WaitPendingPublishes()
	requireProbeUnauthorizedEventually(t, p.opts, p.plain, revocationSLA(t))
	if elapsed := time.Since(start); elapsed > revocationSLA(t) {
		t.Fatalf("revocation SLA exceeded: %v (limit %v)", elapsed, revocationSLA(t))
	}
}

// SEC7.3: IBEX_AUTH_CACHE_ENABLED without Redis must not wrap LRU (no stale allow).
func TestSecurity_SEC7_3_AuthCacheEnabledWithoutRedisImmediateRevoke(t *testing.T) {
	env := setupSecurityTestEnv(t, proxyServerOpts{
		defaultRPM: 60, withAuthCache: true, skipRedis: true,
	})
	p := newSec7TokenProbe(t, env, "sec7-no-redis")

	// Two probes must never advertise cache — Redis absent ⇒ no wrap.
	requireProbeOKCached(t, p.opts, false)
	requireProbeOKCached(t, p.opts, false)

	p.revoke(t)
	// Immediate 401 — no LRU stale window without revocation channel.
	requireProbe(t, p.opts, probeExpect{http.StatusUnauthorized, apierror.CodeInvalidToken}, p.plain)
}
