//go:build integration

package proxy_test

import (
	"context"
	"net/http"
	"strings"
	"testing"

	"github.com/Rick1330/ibex-harness/infra/testing/testutil"
	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"google.golang.org/grpc/metadata"
)

func TestProxyAuthIntegration_Tokens(t *testing.T) {
	fx := setupProxyAuthFixture(t)

	t.Run("missing auth", func(t *testing.T) {
		resp, err := http.Get(fx.srv.URL + "/v1/internal/auth-probe")
		if err != nil {
			t.Fatal(err)
		}
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusUnauthorized {
			t.Fatalf("status: %d", resp.StatusCode)
		}
	})

	t.Run("missing agent header on auth-probe", func(t *testing.T) {
		resp, body := authProbeGET(t, authProbeOpts{srvURL: fx.srv.URL, bearer: fx.validBearer})
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusBadRequest || !strings.Contains(body, "MISSING_AGENT_ID") {
			t.Fatalf("status: %d body=%s", resp.StatusCode, body)
		}
	})

	t.Run("valid token", func(t *testing.T) {
		resp, _ := authProbeGET(t, authProbeOpts{srvURL: fx.srv.URL, bearer: fx.validBearer, agentID: fx.agentA})
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusOK {
			t.Fatalf("status: %d", resp.StatusCode)
		}
	})

	t.Run("invalid token", func(t *testing.T) {
		resp, _ := authProbeGET(t, authProbeOpts{srvURL: fx.srv.URL, bearer: fx.validBearer + "wrong"})
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusUnauthorized {
			t.Fatalf("status: %d", resp.StatusCode)
		}
	})

	t.Run("revoked token", func(t *testing.T) {
		resp, _ := authProbeGET(t, authProbeOpts{srvURL: fx.srv.URL, bearer: fx.revokedBearer})
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusUnauthorized {
			t.Fatalf("status: %d", resp.StatusCode)
		}
	})

	t.Run("response headers on 401", func(t *testing.T) {
		resp, err := http.Get(fx.srv.URL + "/v1/internal/auth-probe")
		if err != nil {
			t.Fatal(err)
		}
		defer resp.Body.Close()
		assertResponseHeaders(t, resp)
	})

	t.Run("revoke via grpc then reject", func(t *testing.T) {
		admin := testutil.SeedBootstrapAdminToken(t, fx.db, fx.orgA)
		createCtx := metadata.NewOutgoingContext(context.Background(), metadata.Pairs("authorization", "Bearer "+admin))
		createResp, err := fx.authFx.Client.CreateToken(createCtx, &authv1.CreateTokenRequest{
			OrgId:       fx.orgA,
			Name:        "revoke-me",
			Type:        authv1.TokenType_TOKEN_TYPE_PAT,
			Permissions: 42,
		})
		if err != nil {
			t.Fatalf("create: %v", err)
		}
		plain := createResp.GetPlaintext()
		resp, _ := authProbeGET(t, authProbeOpts{srvURL: fx.srv.URL, bearer: plain, agentID: fx.agentA})
		resp.Body.Close()
		if resp.StatusCode != http.StatusOK {
			t.Fatalf("pre-revoke status: %d", resp.StatusCode)
		}

		_, err = fx.authFx.Client.RevokeToken(createCtx, &authv1.RevokeTokenRequest{
			OrgId:   fx.orgA,
			TokenId: createResp.GetTokenId(),
		})
		if err != nil {
			t.Fatalf("revoke: %v", err)
		}

		resp2, _ := authProbeGET(t, authProbeOpts{srvURL: fx.srv.URL, bearer: plain})
		defer resp2.Body.Close()
		if resp2.StatusCode != http.StatusUnauthorized {
			t.Fatalf("post-revoke status: %d", resp2.StatusCode)
		}
	})
}
