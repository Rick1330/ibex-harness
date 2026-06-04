//go:build integration

package proxy_test

import (
	"context"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/infra/testing/testutil"
	"github.com/Rick1330/ibex-harness/packages/permissions"
	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"github.com/Rick1330/ibex-harness/services/auth/integrationtest"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/config"
	proxyhttp "github.com/Rick1330/ibex-harness/services/proxy/internal/http"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/metrics"
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
	validator := auth.NewGRPCValidator(authv1.NewAuthServiceClient(conn), cfg.AuthValidateTimeout)
	handler := proxyhttp.NewRouter(cfg, slog.New(slog.NewTextHandler(io.Discard, nil)), metrics.New(), validator)
	return httptest.NewServer(handler)
}

func TestProxyAuthIntegration(t *testing.T) {
	dsn, cleanup := testutil.SetupPostgres(t)
	defer cleanup()

	db := testutil.OpenDB(t, dsn)
	defer db.Close()

	authFx := integrationtest.StartAuthGRPC(t, dsn)
	defer authFx.Close()

	orgA := testutil.SeedOrganization(t, db, "Org A", "org-a-proxy-"+uuid.NewString()[:8])
	orgB := testutil.SeedOrganization(t, db, "Org B", "org-b-proxy-"+uuid.NewString()[:8])

	validBearer, _ := testutil.SeedToken(t, db, orgA, 42)
	chatBearer, _ := testutil.SeedToken(t, db, orgA, permissions.ProxyChatCompletion)
	revokedBearer := testutil.SeedTokenRevoked(t, db, orgA, uuid.New(), 42)
	orgBBearer, _ := testutil.SeedToken(t, db, orgB, 42)
	lowPermsBearer, _ := testutil.SeedToken(t, db, orgA, permissions.ReadOnly)

	srv := startProxyServer(t, authFx.Addr)
	defer srv.Close()

	t.Run("missing auth", func(t *testing.T) {
		resp, err := http.Get(srv.URL + "/v1/internal/auth-probe")
		if err != nil {
			t.Fatal(err)
		}
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusUnauthorized {
			t.Fatalf("status: %d", resp.StatusCode)
		}
	})

	t.Run("valid token", func(t *testing.T) {
		req, _ := http.NewRequest(http.MethodGet, srv.URL+"/v1/internal/auth-probe", nil)
		req.Header.Set("Authorization", "Bearer "+validBearer)
		resp, err := http.DefaultClient.Do(req)
		if err != nil {
			t.Fatal(err)
		}
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusOK {
			body, _ := io.ReadAll(resp.Body)
			t.Fatalf("status: %d body=%s", resp.StatusCode, string(body))
		}
	})

	t.Run("invalid token", func(t *testing.T) {
		req, _ := http.NewRequest(http.MethodGet, srv.URL+"/v1/internal/auth-probe", nil)
		req.Header.Set("Authorization", "Bearer "+validBearer+"wrong")
		resp, err := http.DefaultClient.Do(req)
		if err != nil {
			t.Fatal(err)
		}
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusUnauthorized {
			t.Fatalf("status: %d", resp.StatusCode)
		}
	})

	t.Run("revoked token", func(t *testing.T) {
		req, _ := http.NewRequest(http.MethodGet, srv.URL+"/v1/internal/auth-probe", nil)
		req.Header.Set("Authorization", "Bearer "+revokedBearer)
		resp, err := http.DefaultClient.Do(req)
		if err != nil {
			t.Fatal(err)
		}
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusUnauthorized {
			t.Fatalf("status: %d", resp.StatusCode)
		}
	})

	t.Run("cross tenant path", func(t *testing.T) {
		req, _ := http.NewRequest(http.MethodGet, srv.URL+"/v1/orgs/"+orgB+"/auth-probe", nil)
		req.Header.Set("Authorization", "Bearer "+validBearer)
		resp, err := http.DefaultClient.Do(req)
		if err != nil {
			t.Fatal(err)
		}
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusForbidden {
			t.Fatalf("status: %d", resp.StatusCode)
		}
	})

	t.Run("matching org path", func(t *testing.T) {
		req, _ := http.NewRequest(http.MethodGet, srv.URL+"/v1/orgs/"+orgA+"/auth-probe", nil)
		req.Header.Set("Authorization", "Bearer "+validBearer)
		resp, err := http.DefaultClient.Do(req)
		if err != nil {
			t.Fatal(err)
		}
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusOK {
			t.Fatalf("status: %d", resp.StatusCode)
		}
	})

	t.Run("chat without permission", func(t *testing.T) {
		req, _ := http.NewRequest(http.MethodPost, srv.URL+"/v1/chat/completions", strings.NewReader("{}"))
		req.Header.Set("Authorization", "Bearer "+lowPermsBearer)
		resp, err := http.DefaultClient.Do(req)
		if err != nil {
			t.Fatal(err)
		}
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusForbidden {
			t.Fatalf("status: %d", resp.StatusCode)
		}
	})

	t.Run("chat stub with permission", func(t *testing.T) {
		req, _ := http.NewRequest(http.MethodPost, srv.URL+"/v1/chat/completions", strings.NewReader("{}"))
		req.Header.Set("Authorization", "Bearer "+chatBearer)
		resp, err := http.DefaultClient.Do(req)
		if err != nil {
			t.Fatal(err)
		}
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusNotImplemented {
			t.Fatalf("status: %d", resp.StatusCode)
		}
	})

	t.Run("revoke via grpc then reject", func(t *testing.T) {
		admin := testutil.SeedBootstrapAdminToken(t, db, orgA)
		createCtx := metadata.NewOutgoingContext(context.Background(), metadata.Pairs("authorization", "Bearer "+admin))
		createResp, err := authFx.Client.CreateToken(createCtx, &authv1.CreateTokenRequest{
			OrgId:       orgA,
			Name:        "revoke-me",
			Type:        authv1.TokenType_TOKEN_TYPE_PAT,
			Permissions: 42,
		})
		if err != nil {
			t.Fatalf("create: %v", err)
		}
		plain := createResp.GetPlaintext()
		req, _ := http.NewRequest(http.MethodGet, srv.URL+"/v1/internal/auth-probe", nil)
		req.Header.Set("Authorization", "Bearer "+plain)
		resp, err := http.DefaultClient.Do(req)
		if err != nil {
			t.Fatal(err)
		}
		resp.Body.Close()
		if resp.StatusCode != http.StatusOK {
			t.Fatalf("pre-revoke status: %d", resp.StatusCode)
		}

		_, err = authFx.Client.RevokeToken(createCtx, &authv1.RevokeTokenRequest{
			OrgId:   orgA,
			TokenId: createResp.GetTokenId(),
		})
		if err != nil {
			t.Fatalf("revoke: %v", err)
		}

		req2, _ := http.NewRequest(http.MethodGet, srv.URL+"/v1/internal/auth-probe", nil)
		req2.Header.Set("Authorization", "Bearer "+plain)
		resp2, err := http.DefaultClient.Do(req2)
		if err != nil {
			t.Fatal(err)
		}
		defer resp2.Body.Close()
		if resp2.StatusCode != http.StatusUnauthorized {
			t.Fatalf("post-revoke status: %d", resp2.StatusCode)
		}
	})

	t.Run("org b token on org b path", func(t *testing.T) {
		req, _ := http.NewRequest(http.MethodGet, srv.URL+"/v1/orgs/"+orgB+"/auth-probe", nil)
		req.Header.Set("Authorization", "Bearer "+orgBBearer)
		resp, err := http.DefaultClient.Do(req)
		if err != nil {
			t.Fatal(err)
		}
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusOK {
			t.Fatalf("status: %d", resp.StatusCode)
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
