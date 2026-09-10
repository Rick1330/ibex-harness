//go:build integration

package proxy_test

import (
	"context"
	"database/sql"
	"encoding/base64"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/infra/testing/testutil"
	ibexcrypto "github.com/Rick1330/ibex-harness/packages/crypto"
	"github.com/Rick1330/ibex-harness/packages/permissions"
	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/services/auth/integrationtest"
	"github.com/google/uuid"
	"google.golang.org/grpc/metadata"
)

// captureOpenAI records Complete requests so tests can assert BYO overrides
// arrived via a real Auth GetProviderCredential RPC (not a fake client).
type captureOpenAI struct {
	last provider.Request
}

func (c *captureOpenAI) Name() string { return "openai" }
func (c *captureOpenAI) SupportedModels() []string {
	return []string{"gpt-4o"}
}
func (c *captureOpenAI) Complete(_ context.Context, req provider.Request) (provider.Response, error) {
	c.last = req
	return provider.Response{
		StatusCode: http.StatusOK,
		Body: io.NopCloser(strings.NewReader(
			`{"id":"cred-test","object":"chat.completion","choices":[{"index":0,"message":{"role":"assistant","content":"ok"},"finish_reason":"stop"}]}`,
		)),
	}, nil
}

type credProxyFixture struct {
	db        *sql.DB
	authFx    *integrationtest.AuthGRPCFixture
	srv       *httptest.Server
	orgA      string
	orgB      string
	agentA    string
	agentB    string
	chatA     string
	chatB     string
	capture   *captureOpenAI
	byoAPIKey string
}

func setupCredentialProxyFixture(t *testing.T) credProxyFixture {
	t.Helper()
	dsn, cleanup := testutil.SetupPostgres(t)
	t.Cleanup(cleanup)

	db := testutil.OpenDB(t, dsn)
	t.Cleanup(func() { _ = db.Close() })

	master := base64.StdEncoding.EncodeToString(ibexcrypto.GenerateRandomBytes(ibexcrypto.MasterKeySize))
	authFx := integrationtest.StartAuthGRPCWithCredentials(t, dsn, master)
	t.Cleanup(authFx.Close)

	orgA := testutil.SeedOrganization(t, db, "Cred Org A", "cred-a-"+uuid.NewString()[:8])
	orgB := testutil.SeedOrganization(t, db, "Cred Org B", "cred-b-"+uuid.NewString()[:8])
	userA := testutil.SeedUser(t, db, orgA, "cred-a-"+uuid.NewString()[:8]+"@example.com", "Cred A")
	userB := testutil.SeedUser(t, db, orgB, "cred-b-"+uuid.NewString()[:8]+"@example.com", "Cred B")
	agentA := testutil.SeedAgent(t, db, orgA, userA, "Agent A", "agent-a-"+uuid.NewString()[:8])
	agentB := testutil.SeedAgent(t, db, orgB, userB, "Agent B", "agent-b-"+uuid.NewString()[:8])

	adminA := testutil.SeedBootstrapAdminToken(t, db, orgA)
	chatA, _ := testutil.SeedToken(t, db, orgA, permissions.ProxyChatCompletion)
	chatB, _ := testutil.SeedToken(t, db, orgB, permissions.ProxyChatCompletion)

	cap := &captureOpenAI{}
	srv := startProxyServer(t, authFx.Addr, proxyServerOpts{
		providers:              []provider.Provider{cap},
		withCredentialResolver: true,
	})
	t.Cleanup(srv.Close)

	const byoKey = "sk-byo-integration-abcdef"
	mustCreateOrgCredential(t, authFx, orgCredSeed{admin: adminA, orgID: orgA, apiKey: byoKey})

	return credProxyFixture{
		db: db, authFx: authFx, srv: srv,
		orgA: orgA, orgB: orgB, agentA: agentA, agentB: agentB,
		chatA: chatA, chatB: chatB, capture: cap, byoAPIKey: byoKey,
	}
}

type orgCredSeed struct {
	admin, orgID, apiKey string
}

func mustCreateOrgCredential(t *testing.T, authFx *integrationtest.AuthGRPCFixture, seed orgCredSeed) {
	t.Helper()
	ctx, cancel := context.WithTimeout(
		metadata.NewOutgoingContext(context.Background(), metadata.Pairs(
			"authorization", "Bearer "+seed.admin,
		)),
		5*time.Second,
	)
	defer cancel()
	_, err := authFx.Client.CreateProviderCredential(ctx, &authv1.CreateProviderCredentialRequest{
		OrgId: seed.orgID, ProviderName: "openai", ApiKey: seed.apiKey, BaseUrl: "https://byo.example/v1",
	})
	if err != nil {
		t.Fatalf("CreateProviderCredential: %v", err)
	}
}

func TestProxyAuthIntegration_GetProviderCredential_BYOAndPlatformDefault(t *testing.T) {
	fx := setupCredentialProxyFixture(t)
	body := `{"model":"gpt-4o","messages":[{"role":"user","content":"hi"}]}`

	// Credential-found: org A sealed row → chat Complete sees BYO override from real Get RPC.
	fx.capture.last = provider.Request{}
	resp, respBody := chatPOST(t, chatRequestOpts{
		srvURL: fx.srv.URL, bearer: fx.chatA, agentID: fx.agentA,
		contentType: "application/json", body: body,
	})
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("BYO chat status=%d body=%s", resp.StatusCode, respBody)
	}
	if fx.capture.last.APIKeyOverride != fx.byoAPIKey {
		t.Fatalf("BYO APIKeyOverride=%q want %q (GetProviderCredential RPC round-trip)",
			fx.capture.last.APIKeyOverride, fx.byoAPIKey)
	}
	if fx.capture.last.BaseURLOverride != "https://byo.example/v1" {
		t.Fatalf("BaseURLOverride=%q", fx.capture.last.BaseURLOverride)
	}

	// No-row / platform-default: org B has no credential → no override.
	fx.capture.last = provider.Request{}
	resp2, respBody2 := chatPOST(t, chatRequestOpts{
		srvURL: fx.srv.URL, bearer: fx.chatB, agentID: fx.agentB,
		contentType: "application/json", body: body,
	})
	defer resp2.Body.Close()
	if resp2.StatusCode != http.StatusOK {
		t.Fatalf("platform-default chat status=%d body=%s", resp2.StatusCode, respBody2)
	}
	if fx.capture.last.APIKeyOverride != "" {
		t.Fatalf("platform-default APIKeyOverride=%q want empty", fx.capture.last.APIKeyOverride)
	}
	if fx.capture.last.BaseURLOverride != "" {
		t.Fatalf("platform-default BaseURLOverride=%q want empty", fx.capture.last.BaseURLOverride)
	}
}
