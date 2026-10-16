package http

import (
	"context"
	"net/http"
	"net/http/httptest"
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
func (p *responsesTestProvider) CreateResponse(context.Context, responses.Request, string, string, string) (responses.Response, error) {
	p.calls++
	return responses.ParseResponse([]byte(`{"id":"r","status":"completed","usage":{"input_tokens":1,"output_tokens":1,"total_tokens":2},"output":[]}`))
}

const routeTestManifest = `{"version":"provider-capability-manifest.v1","generated_at":"2026-01-01T00:00:00Z","expires_at":"2099-01-01T00:00:00Z","models":[{"provider":"openai","model":"gpt-4o","context_window":128000,"max_output_tokens":16384,"tokenizer_family":"o200k_base","endpoint":"/v1/responses","capabilities":{"responses":{"state":"supported","provenance":{"source_url":"https://example.com/responses","title":"Responses","accessed_at":"2026-01-01T00:00:00Z"}},"reasoning":{"state":"unverified"}}}]}`

func routeTestSnapshot(t *testing.T) *providercap.Snapshot {
	t.Helper()
	s, err := providercap.LoadBytes([]byte(routeTestManifest), time.Date(2026, 1, 2, 0, 0, 0, 0, time.UTC))
	if err != nil {
		t.Fatal(err)
	}
	return s
}

func TestResponsesCapabilityGateDeniesBeforeDispatch(t *testing.T) {
	p := &responsesTestProvider{}
	req := httptest.NewRequest(http.MethodPost, "/v1/responses", nil)
	ctx := llm.WithResponsesRequest(req.Context(), responses.Request{Model: "gpt-4o", Stream: true})
	ctx = provider.WithProvider(ctx, p)
	rr := httptest.NewRecorder()
	ResponsesCapabilityMiddleware(routeTestSnapshot(t), "")(http.HandlerFunc(func(http.ResponseWriter, *http.Request) { t.Fatal("downstream must not run") })).ServeHTTP(rr, req.WithContext(ctx))
	if rr.Code != http.StatusUnprocessableEntity || p.calls != 0 {
		t.Fatalf("status=%d calls=%d body=%s", rr.Code, p.calls, rr.Body.String())
	}
}

func TestResponsesCapabilityGateAllowsVerifiedModel(t *testing.T) {
	p := &responsesTestProvider{}
	req := httptest.NewRequest(http.MethodPost, "/v1/responses", nil)
	ctx := llm.WithResponsesRequest(req.Context(), responses.Request{Model: "gpt-4o"})
	ctx = provider.WithProvider(ctx, p)
	rr := httptest.NewRecorder()
	ResponsesCapabilityMiddleware(routeTestSnapshot(t), "")(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { w.WriteHeader(http.StatusNoContent) })).ServeHTTP(rr, req.WithContext(ctx))
	if rr.Code != http.StatusNoContent {
		t.Fatalf("status=%d body=%s", rr.Code, rr.Body.String())
	}
}

func TestResponsesCapabilityGateDeniesUnsupportedField(t *testing.T) {
	req := httptest.NewRequest(http.MethodPost, "/v1/responses", nil)
	ctx := llm.WithResponsesRequest(req.Context(), responses.Request{Model: "gpt-4o", Reasoning: &responses.Reasoning{Effort: "low"}})
	ctx = provider.WithProvider(ctx, &responsesTestProvider{})
	rr := httptest.NewRecorder()
	ResponsesCapabilityMiddleware(routeTestSnapshot(t), "")(http.HandlerFunc(func(http.ResponseWriter, *http.Request) { t.Fatal("downstream must not run") })).ServeHTTP(rr, req.WithContext(ctx))
	if rr.Code != http.StatusServiceUnavailable {
		t.Fatalf("status=%d body=%s", rr.Code, rr.Body.String())
	}
}

func TestHandleResponsesRejectsNonPostBeforeProvider(t *testing.T) {
	p := &responsesTestProvider{}
	req := httptest.NewRequest(http.MethodGet, "/v1/responses", nil)
	ctx := provider.WithProvider(req.Context(), p)
	ctx = llm.WithResponsesRequest(ctx, responses.Request{Model: "gpt-4o"})
	rr := httptest.NewRecorder()
	handleResponses(rr, req.WithContext(ctx), protectedRouteDeps{})
	if rr.Code != http.StatusMethodNotAllowed || p.calls != 0 {
		t.Fatalf("status=%d calls=%d", rr.Code, p.calls)
	}
}
