//go:build integration

package proxy_test

import (
	"context"
	"database/sql"
	"github.com/Rick1330/ibex-harness/packages/logger"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/infra/testing/testutil"
	"github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/packages/permissions"
	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"github.com/Rick1330/ibex-harness/packages/ratelimit"
	"github.com/Rick1330/ibex-harness/packages/telemetry"
	"github.com/Rick1330/ibex-harness/services/auth/integrationtest"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/config"
	proxygrpc "github.com/Rick1330/ibex-harness/services/proxy/internal/grpc"
	proxyhttp "github.com/Rick1330/ibex-harness/services/proxy/internal/http"
	"github.com/google/uuid"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
)

type proxyAuthFixture struct {
	db             *sql.DB
	authFx         *integrationtest.AuthGRPCFixture
	srv            *httptest.Server
	orgA           string
	orgB           string
	agentA         string
	agentB         string
	validBearer    string
	chatBearer     string
	revokedBearer  string
	orgBBearer     string
	lowPermsBearer string
}

func setupProxyAuthFixture(t *testing.T) proxyAuthFixture {
	t.Helper()
	dsn, cleanup := testutil.SetupPostgres(t)
	t.Cleanup(cleanup)

	db := testutil.OpenDB(t, dsn)
	t.Cleanup(func() { _ = db.Close() })

	authFx := integrationtest.StartAuthGRPC(t, dsn)
	t.Cleanup(authFx.Close)

	orgA := testutil.SeedOrganization(t, db, "Org A", "org-a-proxy-"+uuid.NewString()[:8])
	orgB := testutil.SeedOrganization(t, db, "Org B", "org-b-proxy-"+uuid.NewString()[:8])
	userA := testutil.SeedUser(t, db, orgA, "user-a-"+uuid.NewString()[:8]+"@example.com", "User A")
	userB := testutil.SeedUser(t, db, orgB, "user-b-"+uuid.NewString()[:8]+"@example.com", "User B")
	agentA := testutil.SeedAgent(t, db, orgA, userA, "Agent A", "agent-a-"+uuid.NewString()[:8])
	agentB := testutil.SeedAgent(t, db, orgB, userB, "Agent B", "agent-b-"+uuid.NewString()[:8])

	validBearer, _ := testutil.SeedToken(t, db, orgA, 42)
	chatBearer, _ := testutil.SeedToken(t, db, orgA, permissions.ProxyChatCompletion)
	revokedBearer := testutil.SeedTokenRevoked(t, db, orgA, uuid.New(), 42)
	orgBBearer, _ := testutil.SeedToken(t, db, orgB, 42)
	lowPermsBearer, _ := testutil.SeedToken(t, db, orgA, permissions.ReadOnly)

	srv := startProxyServer(t, authFx.Addr)
	t.Cleanup(srv.Close)

	return proxyAuthFixture{
		db: db, authFx: authFx, srv: srv,
		orgA: orgA, orgB: orgB, agentA: agentA, agentB: agentB,
		validBearer: validBearer, chatBearer: chatBearer, revokedBearer: revokedBearer,
		orgBBearer: orgBBearer, lowPermsBearer: lowPermsBearer,
	}
}

func startProxyServer(t *testing.T, authAddr string) *httptest.Server {
	t.Helper()
	conn, err := grpc.NewClient(authAddr,
		grpc.WithTransportCredentials(insecure.NewCredentials()),
		grpc.WithChainUnaryInterceptor(proxygrpc.RequestIDUnaryInterceptor()),
	)
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
		Logger:        logger.Discard("proxy"),
		Metrics:       metrics.NewProxy("test"),
		Tracer:        telemetry.NoopTracer("proxy"),
		Validator:     validator,
		AgentVerifier: agentVerifier,
		Limiter:       ratelimit.Noop(),
	})
	return httptest.NewServer(handler)
}

type authProbeOpts struct {
	srvURL  string
	bearer  string
	agentID string
}

func authProbeGET(t *testing.T, opts authProbeOpts) (*http.Response, string) {
	t.Helper()
	return authenticatedGET(t, opts.srvURL+"/v1/internal/auth-probe", opts.bearer, opts.agentID)
}

type orgAuthProbeOpts struct {
	srvURL  string
	orgID   string
	bearer  string
	agentID string
}

func orgAuthProbeGET(t *testing.T, opts orgAuthProbeOpts) (*http.Response, string) {
	t.Helper()
	return authenticatedGET(t, opts.srvURL+"/v1/orgs/"+opts.orgID+"/auth-probe", opts.bearer, opts.agentID)
}

func authenticatedGET(t *testing.T, url, bearer, agentID string) (*http.Response, string) {
	t.Helper()
	req, err := http.NewRequest(http.MethodGet, url, nil)
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
	b, _ := io.ReadAll(resp.Body)
	return resp, string(b)
}

type chatRequestOpts struct {
	srvURL      string
	bearer      string
	agentID     string
	contentType string
	body        string
}

func chatPOST(t *testing.T, opts chatRequestOpts) (*http.Response, string) {
	t.Helper()
	req, err := http.NewRequest(http.MethodPost, opts.srvURL+"/v1/chat/completions", strings.NewReader(opts.body))
	if err != nil {
		t.Fatal(err)
	}
	if opts.bearer != "" {
		req.Header.Set("Authorization", "Bearer "+opts.bearer)
	}
	if opts.contentType != "" {
		req.Header.Set("Content-Type", opts.contentType)
	}
	if opts.agentID != "" {
		req.Header.Set("X-IBEX-Agent-ID", opts.agentID)
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	b, _ := io.ReadAll(resp.Body)
	return resp, string(b)
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
