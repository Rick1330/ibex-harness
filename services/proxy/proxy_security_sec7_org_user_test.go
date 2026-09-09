//go:build integration

package proxy_test

import (
	"context"
	"database/sql"
	"fmt"
	"io"
	"net/http"
	"sync"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/infra/testing/testutil"
	apierror "github.com/Rick1330/ibex-harness/packages/apierror"
	"github.com/Rick1330/ibex-harness/packages/permissions"
	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"github.com/Rick1330/ibex-harness/packages/revocation"
	"github.com/redis/go-redis/v9"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"google.golang.org/grpc/metadata"
)

// productSuspensionSLA is the milestone 4.A.2 exit gate (same bound as token revocation).
const productSuspensionSLA = 5 * time.Second

type probeForbiddenOpts struct {
	opts   authProbeOpts
	secret string
	want   apierror.Code
	within time.Duration
}

func tryAuthProbeGET(opts authProbeOpts) (*http.Response, string, error) {
	req, err := http.NewRequest(http.MethodGet, opts.srvURL+"/v1/internal/auth-probe", nil)
	if err != nil {
		return nil, "", err
	}
	if opts.bearer != "" {
		req.Header.Set("Authorization", "Bearer "+opts.bearer)
	}
	if opts.agentID != "" {
		req.Header.Set("X-IBEX-Agent-ID", opts.agentID)
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return nil, "", err
	}
	b, err := io.ReadAll(resp.Body)
	if err != nil {
		resp.Body.Close()
		return nil, "", err
	}
	return resp, string(b), nil
}

func requireProbeForbiddenEventually(t *testing.T, p probeForbiddenOpts) {
	t.Helper()
	var (
		mu            sync.Mutex
		lastStatus    int
		lastBody      string
		forbiddenResp *http.Response
		forbiddenBody string
	)
	require.EventuallyWithT(t, func(c *assert.CollectT) {
		resp, body, err := tryAuthProbeGET(p.opts)
		mu.Lock()
		defer mu.Unlock()
		if err != nil {
			lastBody = err.Error()
			assert.Fail(c, fmt.Sprintf("auth probe error: %v", err))
			return
		}
		lastStatus = resp.StatusCode
		lastBody = body
		if resp.StatusCode == http.StatusForbidden {
			forbiddenResp = resp
			forbiddenBody = body
			return
		}
		resp.Body.Close()
		assert.Fail(c, fmt.Sprintf(
			"expected forbidden within %v; last status=%d body=%s",
			p.within, lastStatus, redactBearer(lastBody, p.opts.bearer),
		))
	}, p.within, 10*time.Millisecond)

	mu.Lock()
	resp := forbiddenResp
	body := forbiddenBody
	mu.Unlock()
	require.NotNil(t, resp, "forbidden response missing after Eventually")
	defer resp.Body.Close()
	requireErrorCode(t, body, p.want)
	assertSecurityErrorEnvelope(t, resp, body, p.secret)
}

func suspendOrgInDB(t *testing.T, db *sql.DB, orgID string) {
	t.Helper()
	ctx := context.Background()
	err := testutil.WithServiceAccount(ctx, db, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(ctx, `
			UPDATE ibex_core.organizations
			SET status = 'suspended'
			WHERE id = $1::uuid`, orgID)
		return err
	})
	if err != nil {
		t.Fatalf("suspend org: %v", err)
	}
}

func publishOrgSuspend(t *testing.T, mrAddr string, orgID string) {
	t.Helper()
	client := redis.NewClient(&redis.Options{Addr: mrAddr})
	t.Cleanup(func() { _ = client.Close() })
	raw, err := (revocation.RevocationEvent{
		Version:   revocation.CurrentSchemaVersion,
		EventType: revocation.EventTypeOrgSuspend,
		OrgID:     orgID,
		RevokedAt: time.Now().UTC(),
	}).Marshal()
	if err != nil {
		t.Fatalf("marshal org_suspend: %v", err)
	}
	if err := client.Publish(context.Background(), revocation.Channel, string(raw)).Err(); err != nil {
		t.Fatalf("publish org_suspend: %v", err)
	}
}

// TestSecurity_SEC7_4_OrgSuspendInvalidatesAuthCacheWithin5s exercises the
// milestone 4.A.2 success signal: after org suspend + ADR-0029 org_suspend
// pub/sub, proxy auth-cache probes return ORG_SUSPENDED within 5s.
func TestSecurity_SEC7_4_OrgSuspendInvalidatesAuthCacheWithin5s(t *testing.T) {
	env := setupSecurityTestEnv(t, proxyServerOpts{defaultRPM: 60, withAuthCache: true})
	if env.redisMR == nil {
		t.Fatal("expected miniredis for auth-cache env")
	}
	p := newSec7TokenProbe(t, env, "sec7-org-suspend")

	requireProbeOKCached(t, p.opts, false)
	requireProbeOKCached(t, p.opts, true)

	start := time.Now()
	suspendOrgInDB(t, env.db, env.orgA.OrgID)
	publishOrgSuspend(t, env.redisMR.Addr(), env.orgA.OrgID)
	requireProbeForbiddenEventually(t, probeForbiddenOpts{
		opts:   p.opts,
		secret: p.plain,
		want:   apierror.CodeOrgSuspended,
		within: productSuspensionSLA,
	})
	elapsed := time.Since(start)
	t.Logf("org_suspend_propagation_latency_ms=%d (limit_ms=%d)", elapsed.Milliseconds(), productSuspensionSLA.Milliseconds())
	if elapsed > productSuspensionSLA {
		t.Fatalf("suspension SLA exceeded: %v (limit %v)", elapsed, productSuspensionSLA)
	}
}

const realisticPATCountPerUser = 8

type ownedPAT struct {
	tokenID string
	plain   string
	opts    authProbeOpts
}

// TestSecurity_SEC7_5_UserDeleteRevokeLoopAuthCache mirrors DELETE /v1/users/{id}
// revoke-before-soft-delete: RevokeToken for every PAT owned by the user, then
// assert proxy auth-cache rejects. Records revoke-loop latency for the deferred
// RevokeAllTokensForUser batch-RPC decision.
func TestSecurity_SEC7_5_UserDeleteRevokeLoopAuthCache(t *testing.T) {
	env := setupSecurityTestEnv(t, proxyServerOpts{defaultRPM: 60, withAuthCache: true})
	memberID := testutil.SeedUser(t, env.db,
		env.orgA.OrgID,
		fmt.Sprintf("member-%s@example.com", env.orgA.OrgID[:8]),
		"Member",
	)
	admin := testutil.SeedBootstrapAdminToken(t, env.db, env.orgA.OrgID)
	authMD := metadata.Pairs("authorization", "Bearer "+admin)

	pats := mintUserPATs(t, mintPATRequest{
		env: env, authMD: authMD, userID: memberID, count: realisticPATCountPerUser,
	})
	warmPATCache(t, pats)

	start := time.Now()
	revokeUserPATs(t, env, authMD, pats)
	env.authFx.WaitPendingPublishes()
	revokeLoopElapsed := time.Since(start)
	t.Logf(
		"user_delete_revoke_loop pats=%d latency_ms=%d p95_threshold_ms=200",
		realisticPATCountPerUser,
		revokeLoopElapsed.Milliseconds(),
	)

	testutil.SoftDeleteUser(t, env.db, env.orgA.OrgID, memberID)
	assertPATsUnauthorized(t, pats, userDeleteAuthCacheDeadline(t))

	if revokeLoopElapsed.Milliseconds() > 200 {
		t.Logf("NOTE: revoke-loop latency %dms exceeds documented 200ms batch-RPC threshold; consider RevokeAllTokensForUser", revokeLoopElapsed.Milliseconds())
	}
}

type mintPATRequest struct {
	env    securityTestEnv
	authMD metadata.MD
	userID string
	count  int
}

func mintUserPATs(t *testing.T, req mintPATRequest) []ownedPAT {
	t.Helper()
	pats := make([]ownedPAT, 0, req.count)
	for i := 0; i < req.count; i++ {
		rpcCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		ctx := metadata.NewOutgoingContext(rpcCtx, req.authMD)
		uid := req.userID
		createResp, err := req.env.authFx.Client.CreateToken(ctx, &authv1.CreateTokenRequest{
			OrgId:       req.env.orgA.OrgID,
			Name:        fmt.Sprintf("user-delete-pat-%d", i),
			Type:        authv1.TokenType_TOKEN_TYPE_PAT,
			Permissions: permissions.ProxyChatCompletion,
			UserId:      &uid,
		})
		cancel()
		if err != nil {
			t.Fatalf("create pat %d: %v", i, err)
		}
		plain := createResp.GetPlaintext()
		pats = append(pats, ownedPAT{
			tokenID: createResp.GetTokenId(),
			plain:   plain,
			opts: authProbeOpts{
				srvURL: req.env.proxy.URL, bearer: plain, agentID: req.env.orgA.AgentID,
			},
		})
	}
	return pats
}

func warmPATCache(t *testing.T, pats []ownedPAT) {
	t.Helper()
	for _, pat := range pats {
		requireProbeOKCached(t, pat.opts, false)
		requireProbeOKCached(t, pat.opts, true)
	}
}

func revokeUserPATs(t *testing.T, env securityTestEnv, authMD metadata.MD, pats []ownedPAT) {
	t.Helper()
	for _, pat := range pats {
		rpcCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		ctx := metadata.NewOutgoingContext(rpcCtx, authMD)
		_, err := env.authFx.Client.RevokeToken(ctx, &authv1.RevokeTokenRequest{
			OrgId: env.orgA.OrgID, TokenId: pat.tokenID, RevokeReason: strPtr("user_deleted"),
		})
		cancel()
		if err != nil {
			t.Fatalf("revoke %s: %v", pat.tokenID, err)
		}
	}
}

func assertPATsUnauthorized(t *testing.T, pats []ownedPAT, within time.Duration) {
	t.Helper()
	for _, pat := range pats {
		requireProbeUnauthorizedEventually(t, pat.opts, pat.plain, within)
	}
}

func userDeleteAuthCacheDeadline(t *testing.T) time.Duration {
	t.Helper()
	deadline := revocationSLA(t)
	if deadline < productSuspensionSLA {
		return productSuspensionSLA
	}
	return deadline
}

func strPtr(s string) *string { return &s }
