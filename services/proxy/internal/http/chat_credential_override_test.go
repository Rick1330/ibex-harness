package http

import (
	"context"
	"encoding/json"
	"errors"
	"net"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	apierror "github.com/Rick1330/ibex-harness/packages/apierror"
	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/packages/ssrf"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/credentials"
	"github.com/google/uuid"
)

type stubCredentialResolver struct {
	result credentials.Result
	err    error
	last   credentials.ResolveInput
}

func (s *stubCredentialResolver) Resolve(_ context.Context, in credentials.ResolveInput) (credentials.Result, error) {
	s.last = in
	if s.err != nil {
		return credentials.Result{}, s.err
	}
	return s.result, nil
}

type captureProvider struct {
	name string
	last provider.Request
}

func (c *captureProvider) Name() string { return c.name }
func (c *captureProvider) SupportedModels() []string {
	return []string{"gpt-4o"}
}
func (c *captureProvider) Complete(_ context.Context, req provider.Request) (provider.Response, error) {
	c.last = req
	return provider.Response{StatusCode: http.StatusOK, Body: http.NoBody}, nil
}

var credTestOrg = uuid.MustParse("11111111-1111-1111-1111-111111111111")

type credOverrideFixture struct {
	handler  chatCompletionHandler
	resolver *stubCredentialResolver
	rec      *httptest.ResponseRecorder
	req      *http.Request
	provReq  *provider.Request
}

func newCredOverrideFixture(t *testing.T, resolver *stubCredentialResolver, withOrg bool) credOverrideFixture {
	t.Helper()
	if resolver == nil {
		resolver = &stubCredentialResolver{}
	}
	h := chatCompletionHandler{log: logger.Discard("proxy"), credentialResolver: resolver}
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", nil)
	req.Header.Set("Authorization", "Bearer ibex_pat_test")
	if withOrg {
		req = req.WithContext(auth.WithContext(req.Context(), &auth.ValidateResult{OrgID: credTestOrg}))
	}
	return credOverrideFixture{
		handler: h, resolver: resolver, rec: rec, req: req, provReq: &provider.Request{},
	}
}

func (f credOverrideFixture) apply() bool {
	return f.handler.applyCredentialOverride(f.rec, f.req, &captureProvider{name: "openai"}, f.provReq)
}

func TestUnit_ApplyCredentialOverride_BYOPropagatesKeyAndBaseURL(t *testing.T) {
	t.Parallel()
	restore := ssrf.SetLookupIPAddrForTest(func(_ context.Context, host string) ([]net.IPAddr, error) {
		if host != "byo.example.test" {
			t.Fatalf("unexpected host %q", host)
		}
		return []net.IPAddr{{IP: net.ParseIP("1.1.1.1")}}, nil
	})
	t.Cleanup(restore)
	fx := newCredOverrideFixture(t, &stubCredentialResolver{result: credentials.Result{
		APIKey: "sk-byo", BaseURL: "https://byo.example.test/v1",
	}}, true)
	if !fx.apply() {
		t.Fatal("expected success")
	}
	assertBYOOverrides(t, fx)
}

func assertBYOOverrides(t *testing.T, fx credOverrideFixture) {
	t.Helper()
	assertBYOKeyAndSNI(t, fx)
	assertBYOPinnedBaseURL(t, fx)
	assertBYOResolveInput(t, fx)
}

func assertBYOKeyAndSNI(t *testing.T, fx credOverrideFixture) {
	t.Helper()
	if fx.provReq.APIKeyOverride != "sk-byo" {
		t.Fatalf("APIKeyOverride=%q", fx.provReq.APIKeyOverride)
	}
	if fx.provReq.TLSServerName != "byo.example.test" {
		t.Fatalf("TLSServerName=%q", fx.provReq.TLSServerName)
	}
}

func assertBYOPinnedBaseURL(t *testing.T, fx credOverrideFixture) {
	t.Helper()
	if !strings.Contains(fx.provReq.BaseURLOverride, "1.1.1.1") {
		t.Fatalf("expected IP-pinned BaseURLOverride, got %q", fx.provReq.BaseURLOverride)
	}
	if strings.Contains(fx.provReq.BaseURLOverride, "byo.example.test") {
		t.Fatalf("expected hostname replaced, got %q", fx.provReq.BaseURLOverride)
	}
}

func assertBYOResolveInput(t *testing.T, fx credOverrideFixture) {
	t.Helper()
	if fx.resolver.last.OrgID != credTestOrg.String() {
		t.Fatalf("resolve org=%q", fx.resolver.last.OrgID)
	}
	if fx.resolver.last.ProviderName != "openai" {
		t.Fatalf("resolve provider=%q", fx.resolver.last.ProviderName)
	}
}

func TestUnit_ApplyCredentialOverride_BlocksPrivateBaseURL(t *testing.T) {
	t.Parallel()
	fx := newCredOverrideFixture(t, &stubCredentialResolver{result: credentials.Result{
		APIKey: "sk-byo", BaseURL: "https://127.0.0.1/v1",
	}}, true)
	ok := fx.apply()
	if ok || fx.rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("ok=%v status=%d", ok, fx.rec.Code)
	}
}

func TestUnit_ApplyCredentialOverride_PlatformDefault(t *testing.T) {
	t.Parallel()
	fx := newCredOverrideFixture(t, &stubCredentialResolver{result: credentials.Result{PlatformDefault: true}}, true)
	if !fx.apply() {
		t.Fatal("expected success")
	}
	if fx.provReq.APIKeyOverride != "" {
		t.Fatalf("APIKeyOverride=%q", fx.provReq.APIKeyOverride)
	}
	if fx.provReq.BaseURLOverride != "" {
		t.Fatalf("BaseURLOverride=%q", fx.provReq.BaseURLOverride)
	}
}

func TestUnit_ApplyCredentialOverride_MissingOrg(t *testing.T) {
	t.Parallel()
	fx := newCredOverrideFixture(t, &stubCredentialResolver{}, false)
	ok := fx.apply()
	if ok || fx.rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("ok=%v status=%d body=%s", ok, fx.rec.Code, fx.rec.Body.String())
	}
	if !strings.Contains(fx.rec.Body.String(), string(apierror.CodeAuthUnavailable)) {
		t.Fatalf("body=%s", fx.rec.Body.String())
	}
}

func TestUnit_ApplyCredentialOverride_InvalidAuth(t *testing.T) {
	t.Parallel()
	fx := newCredOverrideFixture(t, &stubCredentialResolver{}, true)
	fx.req.Header.Del("Authorization")
	ok := fx.apply()
	if ok || fx.rec.Code != http.StatusUnauthorized {
		t.Fatalf("ok=%v status=%d", ok, fx.rec.Code)
	}
}

func TestUnit_ApplyCredentialOverride_ResolverFailure(t *testing.T) {
	t.Parallel()
	fx := newCredOverrideFixture(t, &stubCredentialResolver{err: errors.New("auth down")}, true)
	ok := fx.apply()
	if ok || fx.rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("ok=%v status=%d body=%s", ok, fx.rec.Code, fx.rec.Body.String())
	}
	var envelope map[string]any
	if err := json.Unmarshal(fx.rec.Body.Bytes(), &envelope); err != nil {
		t.Fatal(err)
	}
}

func TestUnit_ApplyCredentialOverride_SkipsMock(t *testing.T) {
	t.Parallel()
	h := chatCompletionHandler{
		credentialResolver: &stubCredentialResolver{err: errors.New("should not run")},
	}
	ok := h.applyCredentialOverride(
		httptest.NewRecorder(),
		httptest.NewRequest(http.MethodPost, "/", nil),
		&captureProvider{name: "mock"},
		&provider.Request{},
	)
	if !ok {
		t.Fatal("mock provider should skip resolve")
	}
}
