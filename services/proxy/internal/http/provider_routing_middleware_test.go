package http

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	apierror "github.com/Rick1330/ibex-harness/packages/apierror"
	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/llm"
)

func TestUnit_ProviderRouting_KnownModelAttachesProvider(t *testing.T) {
	t.Parallel()
	var gotName string
	var called bool
	next := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		called = true
		p, ok := provider.ProviderFromContext(r.Context())
		if !ok {
			t.Fatal("provider missing from context")
		}
		gotName = p.Name()
		w.WriteHeader(http.StatusOK)
	})

	rec := serveProviderRouting(t, "gpt-4o", next)
	if !called {
		t.Fatal("handler not called")
	}
	if gotName != "openai" {
		t.Fatalf("provider=%q", gotName)
	}
	if rec.Code != http.StatusOK {
		t.Fatalf("status: %d", rec.Code)
	}
}

func TestUnit_ProviderRouting_UnknownModel501(t *testing.T) {
	t.Parallel()
	called := false
	next := http.HandlerFunc(func(http.ResponseWriter, *http.Request) {
		called = true
	})

	rec := serveProviderRouting(t, "unknown-model", next)
	if called {
		t.Fatal("handler must not run for unknown model")
	}
	if rec.Code != http.StatusNotImplemented {
		t.Fatalf("status: %d body=%s", rec.Code, rec.Body.String())
	}
	if !strings.Contains(rec.Body.String(), string(apierror.CodeProviderNotConfigured)) {
		t.Fatalf("body: %s", rec.Body.String())
	}
}

func TestUnit_ChatParse_MissingModel400(t *testing.T) {
	t.Parallel()
	called := false
	next := http.HandlerFunc(func(http.ResponseWriter, *http.Request) {
		called = true
	})
	h := ChatParseMiddleware(chatParseOpts{docsBase: ""})(next)

	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions",
		strings.NewReader(`{"model":"","messages":[{"role":"user","content":"hi"}]}`))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if called {
		t.Fatal("handler must not run when validation fails")
	}
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("status: %d body=%s", rec.Code, rec.Body.String())
	}
	body := rec.Body.String()
	if !strings.Contains(body, string(apierror.CodeValidationError)) {
		t.Fatalf("body: %s", body)
	}
	if !strings.Contains(body, `"field":"model"`) {
		t.Fatalf("expected field model error: %s", body)
	}
}

func serveProviderRouting(t *testing.T, model string, next http.Handler) *httptest.ResponseRecorder {
	t.Helper()
	reg, err := provider.NewRegistry(provider.BuiltInCapabilityCatalog(), stubLLMProvider{name: "openai", models: []string{"gpt-4o"}})
	if err != nil {
		t.Fatalf("NewRegistry: %v", err)
	}
	h := ProviderRoutingMiddleware(providerRoutingOpts{
		registry: reg,
		log:      logger.Discard("proxy"),
		docsBase: "",
	})(next)
	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", nil)
	req = req.WithContext(llm.WithChatRequest(req.Context(), &llm.ChatCompletionRequest{
		Model: model, Messages: []llm.Message{{Role: "user", Content: "hi"}},
	}))
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	return rec
}
