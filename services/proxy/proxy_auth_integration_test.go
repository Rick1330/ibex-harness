//go:build integration

package proxy_test

import (
	"context"
	"database/sql"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/infra/testing/testutil"
	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"github.com/Rick1330/ibex-harness/packages/ratelimit"
	"github.com/Rick1330/ibex-harness/services/auth/integrationtest"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/config"
	proxyhttp "github.com/Rick1330/ibex-harness/services/proxy/internal/http"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/metrics"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/validation"
	"github.com/google/uuid"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/metadata"
)

func startProxyServer(t *testing.T, authAddr string) *httptest.Server {
	t.Helper()
	conn, err := grpc.NewClient(authAddr, grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		t.Fatalf("dial auth: %v", err)
	}
	t.Cleanup(func() { _ = conn.Close() })

	cfg := config.Config{
		Environment:         "development",
		ServiceName:         "proxy",
		Port:                "8080",
		RedisURL:            "redis://localhost:6379/0",
		AuthGRPCAddr:        authAddr,
		AuthValidateTimeout: 200 * time.Millisecond,
	}
	client := authv1.NewAuthServiceClient(conn)
	validator := auth.NewGRPCValidator(client, cfg.AuthValidateTimeout)
	agentVerifier := auth.NewGRPCAgentVerifier(client, cfg.AuthValidateTimeout)
	handler := proxyhttp.NewRouter(proxyhttp.RouterDeps{
		Config:        cfg,
		Logger:        slog.New(slog.NewTextHandler(io.Discard, nil)),
		Metrics:       metrics.New(),
		Validator:     validator,
		AgentVerifier: agentVerifier,
		Limiter:       ratelimit.Noop(),
	})
	return httptest.NewServer(handler)
}

func authProbeGET(t *testing.T, srvURL, bearer, agentID string) (*http.Response, string) {
	t.Helper()
	req, err := http.NewRequest(http.MethodGet, srvURL+"/v1/internal/auth-probe", nil)
	if err != nil {
		t.Fatal(err)
	}
	if bearer != "" {
		req.Header.Set("Authorization", "Bearer "+bearer)
	}
	if agentID != "" {
		req.Header.Set("X-IBEX-Agent-ID", agentID)
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	return resp, readBody(resp)
}

func seedPausedAgent(t *testing.T, db *sql.DB, orgID, userID string) string {
	t.Helper()
	pausedID := uuid.New().String()
	err := testutil.WithServiceAccount(context.Background(), db, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(context.Background(), `
			INSERT INTO ibex_core.agents (id, org_id, created_by, name, slug, status)
			VALUES ($1::uuid, $2::uuid, $3::uuid, $4, $5, 'paused')`,
			pausedID, orgID, userID, "Paused Agent", "paused-"+uuid.NewString()[:8],
		)
		return err
	})
	if err != nil {
		t.Fatalf("seed paused agent: %v", err)
	}
	return pausedID
}

func TestProxyAgentVerificationIntegration(t *testing.T) {
	dsn, cleanup := testutil.SetupPostgres(t)
	defer cleanup()

	db := testutil.OpenDB(t, dsn)
	defer db.Close()

	authFx := integrationtest.StartAuthGRPC(t, dsn)
	defer authFx.Close()

	orgA := testutil.SeedOrganization(t, db, "Org A", "org-a-agent-"+uuid.NewString()[:8])
	orgB := testutil.SeedOrganization(t, db, "Org B", "org-b-agent-"+uuid.NewString()[:8])
	userA := testutil.SeedUser(t, db, orgA, "user-a-"+uuid.NewString()[:8]+"@example.com", "User A")
	userB := testutil.SeedUser(t, db, orgB, "user-b-"+uuid.NewString()[:8]+"@example.com", "User B")
	agentA := testutil.SeedAgent(t, db, orgA, userA, "Agent A", "agent-a-"+uuid.NewString()[:8])
	agentB := testutil.SeedAgent(t, db, orgB, userB, "Agent B", "agent-b-"+uuid.NewString()[:8])
	validBearer, _ := testutil.SeedToken(t, db, orgA, 42)

	srv := startProxyServer(t, authFx.Addr)
	defer srv.Close()

	t.Run("missing agent header", func(t *testing.T) {
		resp, body := authProbeGET(t, srv.URL, validBearer, "")
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusBadRequest || !strings.Contains(body, "MISSING_AGENT_ID") {
			t.Fatalf("status=%d body=%s", resp.StatusCode, body)
		}
	})

	t.Run("cross tenant rejected", func(t *testing.T) {
		resp, body := authProbeGET(t, srv.URL, validBearer, agentB)
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusForbidden || !strings.Contains(body, "AGENT_NOT_AUTHORIZED") {
			t.Fatalf("status=%d body=%s", resp.StatusCode, body)
		}
	})

	t.Run("own agent allowed", func(t *testing.T) {
		resp, _ := authProbeGET(t, srv.URL, validBearer, agentA)
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusOK {
			t.Fatalf("status=%d", resp.StatusCode)
		}
	})

	t.Run("paused agent rejected", func(t *testing.T) {
		pausedID := seedPausedAgent(t, db, orgA, userA)
		resp, body := authProbeGET(t, srv.URL, validBearer, pausedID)
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusForbidden || !strings.Contains(body, "AGENT_SUSPENDED") {
			t.Fatalf("status=%d body=%s", resp.StatusCode, body)
		}
	})
}

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
		resp, body := authProbeGET(t, fx.srv.URL, fx.validBearer, "")
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusBadRequest || !strings.Contains(body, "MISSING_AGENT_ID") {
			t.Fatalf("status: %d body=%s", resp.StatusCode, body)
		}
	})

	t.Run("valid token", func(t *testing.T) {
		resp, _ := authProbeGET(t, fx.srv.URL, fx.validBearer, fx.agentA)
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusOK {
			t.Fatalf("status: %d", resp.StatusCode)
		}
	})

	t.Run("invalid token", func(t *testing.T) {
		resp, _ := authProbeGET(t, fx.srv.URL, fx.validBearer+"wrong", "")
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusUnauthorized {
			t.Fatalf("status: %d", resp.StatusCode)
		}
	})

	t.Run("revoked token", func(t *testing.T) {
		resp, _ := authProbeGET(t, fx.srv.URL, fx.revokedBearer, "")
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
		resp, _ := authProbeGET(t, fx.srv.URL, plain, fx.agentA)
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

		resp2, _ := authProbeGET(t, fx.srv.URL, plain, "")
		defer resp2.Body.Close()
		if resp2.StatusCode != http.StatusUnauthorized {
			t.Fatalf("post-revoke status: %d", resp2.StatusCode)
		}
	})
}

func TestProxyAuthIntegration_OrgPaths(t *testing.T) {
	fx := setupProxyAuthFixture(t)

	t.Run("cross tenant path", func(t *testing.T) {
		resp, _ := orgAuthProbeGET(t, fx.srv.URL, fx.orgB, fx.validBearer, "")
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusForbidden {
			t.Fatalf("status: %d", resp.StatusCode)
		}
	})

	t.Run("matching org path", func(t *testing.T) {
		resp, _ := orgAuthProbeGET(t, fx.srv.URL, fx.orgA, fx.validBearer, fx.agentA)
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusOK {
			t.Fatalf("status: %d", resp.StatusCode)
		}
	})

	t.Run("invalid org path uuid", func(t *testing.T) {
		resp, _ := orgAuthProbeGET(t, fx.srv.URL, "not-a-uuid", fx.validBearer, "")
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusBadRequest {
			t.Fatalf("status: %d body=%s", resp.StatusCode, readBody(resp))
		}
	})

	t.Run("org b token on org b path", func(t *testing.T) {
		resp, _ := orgAuthProbeGET(t, fx.srv.URL, fx.orgB, fx.orgBBearer, fx.agentB)
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusOK {
			t.Fatalf("status: %d", resp.StatusCode)
		}
	})
}

func TestProxyAuthIntegration_Chat(t *testing.T) {
	fx := setupProxyAuthFixture(t)

	t.Run("chat without permission", func(t *testing.T) {
		resp, _ := chatPOST(t, fx.srv.URL, fx.lowPermsBearer, fx.agentA, "application/json", "{}")
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusForbidden {
			t.Fatalf("status: %d", resp.StatusCode)
		}
	})

	t.Run("chat stub with permission", func(t *testing.T) {
		body := `{"model":"gpt-4","messages":[{"role":"user","content":"hi"}]}`
		resp, b := chatPOST(t, fx.srv.URL, fx.chatBearer, fx.agentA, "application/json", body)
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusNotImplemented {
			t.Fatalf("status: %d", resp.StatusCode)
		}
		if !strings.Contains(b, "PROVIDER_NOT_CONFIGURED") {
			t.Fatalf("body: %s", b)
		}
		assertResponseHeaders(t, resp)
	})

	t.Run("chat malformed json", func(t *testing.T) {
		resp, b := chatPOST(t, fx.srv.URL, fx.chatBearer, fx.agentA, "application/json", `{invalid`)
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusBadRequest || !strings.Contains(b, "INVALID_JSON") {
			t.Fatalf("status: %d body=%s", resp.StatusCode, b)
		}
	})

	t.Run("chat missing model", func(t *testing.T) {
		body := `{"messages":[{"role":"user","content":"hi"}]}`
		resp, b := chatPOST(t, fx.srv.URL, fx.chatBearer, fx.agentA, "application/json", body)
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusBadRequest {
			t.Fatalf("status: %d body=%s", resp.StatusCode, b)
		}
		if !strings.Contains(b, "VALIDATION_ERROR") || !strings.Contains(b, `"field":"model"`) {
			t.Fatalf("body: %s", b)
		}
		assertResponseHeaders(t, resp)
	})

	t.Run("chat missing agent header", func(t *testing.T) {
		body := `{"model":"gpt-4","messages":[{"role":"user","content":"hi"}]}`
		resp, b := chatPOST(t, fx.srv.URL, fx.chatBearer, "", "application/json", body)
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusBadRequest || !strings.Contains(b, "MISSING_AGENT_ID") {
			t.Fatalf("status: %d body=%s", resp.StatusCode, b)
		}
	})

	t.Run("chat wrong content type", func(t *testing.T) {
		resp, b := chatPOST(t, fx.srv.URL, fx.chatBearer, fx.agentA, "text/plain", `{}`)
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusUnsupportedMediaType || !strings.Contains(b, "UNSUPPORTED_MEDIA_TYPE") {
			t.Fatalf("status: %d body=%s", resp.StatusCode, b)
		}
	})

	t.Run("chat body too large", func(t *testing.T) {
		oversized := strings.Repeat("x", int(validation.MaxRequestBodyBytes+1))
		resp, b := chatPOST(t, fx.srv.URL, fx.chatBearer, fx.agentA, "application/json", oversized)
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusRequestEntityTooLarge || !strings.Contains(b, "PAYLOAD_TOO_LARGE") {
			t.Fatalf("status: %d body=%s", resp.StatusCode, b)
		}
	})
}

func TestProxyAuthUnavailable(t *testing.T) {
	dsn, cleanup := testutil.SetupPostgres(t)
	defer cleanup()

	db := testutil.OpenDB(t, dsn)
	defer db.Close()

	authFx := integrationtest.StartAuthGRPC(t, dsn)
	srv := startProxyServer(t, authFx.Addr)

	orgID := testutil.SeedOrganization(t, db, "Org", "org-down-"+uuid.NewString()[:8])
	validBearer, _ := testutil.SeedToken(t, db, orgID, 42)

	authFx.Close()

	req, _ := http.NewRequest(http.MethodGet, srv.URL+"/v1/internal/auth-probe", nil)
	req.Header.Set("Authorization", "Bearer "+validBearer)
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusServiceUnavailable {
		t.Fatalf("status: %d body=%s", resp.StatusCode, readBody(resp))
	}
	srv.Close()
}

func readBody(resp *http.Response) string {
	b, _ := io.ReadAll(resp.Body)
	return string(b)
}

func assertResponseHeaders(t *testing.T, resp *http.Response) {
	t.Helper()
	if resp.Header.Get("X-Request-ID") == "" {
		t.Fatal("missing X-Request-ID response header")
	}
	if resp.Header.Get("X-Trace-ID") == "" {
		t.Fatal("missing X-Trace-ID response header")
	}
	if resp.Header.Get("X-Response-Time") == "" {
		t.Fatal("missing X-Response-Time response header")
	}
}
