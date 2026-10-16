package http

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/packages/provider/responses"
	"github.com/Rick1330/ibex-harness/packages/providercap"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/llm"
)

type responsesTestProvider struct{ calls int }

func (p *responsesTestProvider) Complete(context.Context, provider.Request) (provider.Response, error) {
	return provider.Response{}, nil
}
func (p *responsesTestProvider) Name() string              { return "openai" }
func (p *responsesTestProvider) SupportedModels() []string { return []string{"gpt-4o"} }
func (p *responsesTestProvider) CreateResponse(context.Context, responses.Request) (responses.Response, error) {
	p.calls++
	return responses.ParseResponse([]byte(`{"id":"r","status":"completed","output":[]}`))
}

func TestResponsesCapabilityGateDeniesBeforeDispatch(t *testing.T) {
	manifest, err := providercap.LoadDefault(time.Now().UTC())
	if err != nil {
		t.Fatal(err)
	}
	p := &responsesTestProvider{}
	req := httptest.NewRequest(http.MethodPost, "/v1/responses", strings.NewReader(`{"model":"gpt-4o","stream":true}`))
	ctx := llm.WithResponsesRequest(req.Context(), responses.Request{Model: "gpt-4o", Stream: true})
	ctx = provider.WithProvider(ctx, p)
	rr := httptest.NewRecorder()
	ResponsesCapabilityMiddleware(manifest, "")(http.HandlerFunc(func(http.ResponseWriter, *http.Request) { t.Fatal("downstream must not run") })).ServeHTTP(rr, req.WithContext(ctx))
	if rr.Code != http.StatusUnprocessableEntity || p.calls != 0 {
		t.Fatalf("status=%d calls=%d body=%s", rr.Code, p.calls, rr.Body.String())
	}
}

func TestResponsesCapabilityGateAllowsVerifiedModel(t *testing.T) {
	manifest, err := providercap.LoadDefault(time.Now().UTC())
	if err != nil {
		t.Fatal(err)
	}
	p := &responsesTestProvider{}
	req := httptest.NewRequest(http.MethodPost, "/v1/responses", nil)
	ctx := llm.WithResponsesRequest(req.Context(), responses.Request{Model: "gpt-4o"})
	ctx = provider.WithProvider(ctx, p)
	rr := httptest.NewRecorder()
	ResponsesCapabilityMiddleware(manifest, "")(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { w.WriteHeader(http.StatusNoContent) })).ServeHTTP(rr, req.WithContext(ctx))
	if rr.Code != http.StatusNoContent {
		t.Fatalf("status=%d body=%s", rr.Code, rr.Body.String())
	}
}
