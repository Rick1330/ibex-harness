package http

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	apierror "github.com/Rick1330/ibex-harness/packages/apierror"
	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/provider"
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

func TestUnit_ApplyCredentialOverride_BYOPropagatesKeyAndBaseURL(t *testing.T) {
	t.Parallel()
	org := uuid.MustParse("11111111-1111-1111-1111-111111111111")
	resolver := &stubCredentialResolver{result: credentials.Result{
		APIKey: "sk-byo", BaseURL: "https://byo.example/v1",
	}}
	h := chatCompletionHandler{
		log: logger.Discard("proxy"), credentialResolver: resolver,
	}
	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", nil)
	req.Header.Set("Authorization", "Bearer ibex_pat_test")
	req = req.WithContext(auth.WithContext(req.Context(), &auth.ValidateResult{OrgID: org}))
	provReq := &provider.Request{}
	ok := h.applyCredentialOverride(httptest.NewRecorder(), req, &captureProvider{name: "openai"}, provReq)
	if !ok {
		t.Fatal("expected success")
	}
	if provReq.APIKeyOverride != "sk-byo" || provReq.BaseURLOverride != "https://byo.example/v1" {
		t.Fatalf("provReq=%+v", provReq)
	}
	if resolver.last.OrgID != org.String() || resolver.last.ProviderName != "openai" {
		t.Fatalf("resolve input=%+v", resolver.last)
	}
}

func TestUnit_ApplyCredentialOverride_PlatformDefault(t *testing.T) {
	t.Parallel()
	org := uuid.MustParse("11111111-1111-1111-1111-111111111111")
	h := chatCompletionHandler{
		log:                logger.Discard("proxy"),
		credentialResolver: &stubCredentialResolver{result: credentials.Result{PlatformDefault: true}},
	}
	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", nil)
	req.Header.Set("Authorization", "Bearer ibex_pat_test")
	req = req.WithContext(auth.WithContext(req.Context(), &auth.ValidateResult{OrgID: org}))
	provReq := &provider.Request{}
	ok := h.applyCredentialOverride(httptest.NewRecorder(), req, &captureProvider{name: "openai"}, provReq)
	if !ok || provReq.APIKeyOverride != "" || provReq.BaseURLOverride != "" {
		t.Fatalf("ok=%v provReq=%+v", ok, provReq)
	}
}

func TestUnit_ApplyCredentialOverride_MissingOrg(t *testing.T) {
	t.Parallel()
	h := chatCompletionHandler{
		log:                logger.Discard("proxy"),
		credentialResolver: &stubCredentialResolver{},
	}
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", nil)
	req.Header.Set("Authorization", "Bearer ibex_pat_test")
	ok := h.applyCredentialOverride(rec, req, &captureProvider{name: "openai"}, &provider.Request{})
	if ok || rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("ok=%v status=%d body=%s", ok, rec.Code, rec.Body.String())
	}
	if !strings.Contains(rec.Body.String(), string(apierror.CodeAuthUnavailable)) {
		t.Fatalf("body=%s", rec.Body.String())
	}
}

func TestUnit_ApplyCredentialOverride_InvalidAuth(t *testing.T) {
	t.Parallel()
	org := uuid.MustParse("11111111-1111-1111-1111-111111111111")
	h := chatCompletionHandler{
		log:                logger.Discard("proxy"),
		credentialResolver: &stubCredentialResolver{},
	}
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", nil)
	req = req.WithContext(auth.WithContext(req.Context(), &auth.ValidateResult{OrgID: org}))
	ok := h.applyCredentialOverride(rec, req, &captureProvider{name: "openai"}, &provider.Request{})
	if ok || rec.Code != http.StatusUnauthorized {
		t.Fatalf("ok=%v status=%d", ok, rec.Code)
	}
}

func TestUnit_ApplyCredentialOverride_ResolverFailure(t *testing.T) {
	t.Parallel()
	org := uuid.MustParse("11111111-1111-1111-1111-111111111111")
	h := chatCompletionHandler{
		log:                logger.Discard("proxy"),
		credentialResolver: &stubCredentialResolver{err: errors.New("auth down")},
	}
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", nil)
	req.Header.Set("Authorization", "Bearer ibex_pat_test")
	req = req.WithContext(auth.WithContext(req.Context(), &auth.ValidateResult{OrgID: org}))
	ok := h.applyCredentialOverride(rec, req, &captureProvider{name: "openai"}, &provider.Request{})
	if ok || rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("ok=%v status=%d body=%s", ok, rec.Code, rec.Body.String())
	}
	var envelope map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &envelope); err != nil {
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
