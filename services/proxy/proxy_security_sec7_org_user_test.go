//go:build integration

package proxy_test

import (
	"context"
	"database/sql"
	"fmt"
	"net/http"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/infra/testing/testutil"
	apierror "github.com/Rick1330/ibex-harness/packages/apierror"
	"github.com/Rick1330/ibex-harness/packages/permissions"
	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"github.com/Rick1330/ibex-harness/packages/revocation"
	"github.com/redis/go-redis/v9"
	"github.com/stretchr/testify/require"
	"google.golang.org/grpc/metadata"
)

// productSuspensionSLA is the milestone 4.A.2 exit gate (same bound as token revocation).
const productSuspensionSLA = 5 * time.Second

func requireProbeForbiddenEventually(t *testing.T, opts authProbeOpts, secret string, want apierror.Code, within time.Duration) {
	t.Helper()
	var lastStatus int
	var lastBody string
	var forbiddenResp *http.Response
	var forbiddenBody string
	require.Eventually(t, func() bool {
		resp, body := authProbeGET(t, opts)
		lastStatus = resp.StatusCode
		lastBody = body
		if resp.StatusCode == http.StatusForbidden {
			forbiddenResp = resp
			forbiddenBody = body
			return true
		}
		resp.Body.Close()
		return false
	}, within, 10*time.Millisecond,
		"expected forbidden within %v; last status=%d body=%s",
		within, lastStatus, redactBearer(lastBody, opts.bearer))
	defer forbiddenResp.Body.Close()
	requireErrorCode(t, forbiddenBody, want)
	assertSecurityErrorEnvelope(t, forbiddenResp, forbiddenBody, secret)
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
	requireProbeForbiddenEventually(t, p.opts, p.plain, apierror.CodeOrgSuspended, productSuspensionSLA)
	elapsed := time.Since(start)
	t.Logf("org_suspend_propagation_latency_ms=%d (limit_ms=%d)", elapsed.Milliseconds(), productSuspensionSLA.Milliseconds())
	if elapsed > productSuspensionSLA {
		t.Fatalf("suspension SLA exceeded: %v (limit %v)", elapsed, productSuspensionSLA)
	}
}

const realisticPATCountPerUser = 8

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

	type ownedPAT struct {
		tokenID string
		plain   string
		opts    authProbeOpts
	}
	pats := make([]ownedPAT, 0, realisticPATCountPerUser)
	for i := 0; i < realisticPATCountPerUser; i++ {
		rpcCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		ctx := metadata.NewOutgoingContext(rpcCtx, authMD)
		uid := memberID
		createResp, err := env.authFx.Client.CreateToken(ctx, &authv1.CreateTokenRequest{
			OrgId:       env.orgA.OrgID,
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
			opts:    authProbeOpts{srvURL: env.proxy.URL, bearer: plain, agentID: env.orgA.AgentID},
		})
	}

	// Warm auth cache for each PAT (same as a live traffic loop before delete).
	for _, pat := range pats {
		requireProbeOKCached(t, pat.opts, false)
		requireProbeOKCached(t, pat.opts, true)
	}

	start := time.Now()
	for _, pat := range pats {
		rpcCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		ctx := metadata.NewOutgoingContext(rpcCtx, authMD)
		if _, err := env.authFx.Client.RevokeToken(ctx, &authv1.RevokeTokenRequest{
			OrgId: env.orgA.OrgID, TokenId: pat.tokenID, RevokeReason: strPtr("user_deleted"),
		}); err != nil {
			cancel()
			t.Fatalf("revoke %s: %v", pat.tokenID, err)
		}
		cancel()
	}
	env.authFx.WaitPendingPublishes()
	revokeLoopElapsed := time.Since(start)
	t.Logf(
		"user_delete_revoke_loop pats=%d latency_ms=%d p95_threshold_ms=200",
		realisticPATCountPerUser,
		revokeLoopElapsed.Milliseconds(),
	)

	// Soft-delete the user row the same way the API does after revoke succeeds.
	softDeleteUser(t, env.db, env.orgA.OrgID, memberID)

	deadline := revocationSLA(t)
	if deadline < productSuspensionSLA {
		// Prefer product SLA for this milestone verification.
		deadline = productSuspensionSLA
	}
	for _, pat := range pats {
		requireProbeUnauthorizedEventually(t, pat.opts, pat.plain, deadline)
	}

	if revokeLoopElapsed.Milliseconds() > 200 {
		t.Logf("NOTE: revoke-loop latency %dms exceeds documented 200ms batch-RPC threshold; consider RevokeAllTokensForUser", revokeLoopElapsed.Milliseconds())
	}
}

func softDeleteUser(t *testing.T, db *sql.DB, orgID, userID string) {
	t.Helper()
	ctx := context.Background()
	err := testutil.WithServiceAccount(ctx, db, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(ctx, `
			UPDATE ibex_core.users
			SET status = 'deactivated', deleted_at = NOW()
			WHERE id = $1::uuid AND org_id = $2::uuid AND deleted_at IS NULL`,
			userID, orgID)
		return err
	})
	if err != nil {
		t.Fatalf("soft-delete user: %v", err)
	}
}

func strPtr(s string) *string { return &s }
