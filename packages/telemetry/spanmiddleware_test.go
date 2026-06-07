package telemetry_test

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/telemetry"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/sdk/trace/tracetest"
)

func TestSpanMiddleware_SpanCreated(t *testing.T) {
	exporter := tracetest.NewInMemoryExporter()
	providers, err := telemetry.InitForTest(exporter)
	if err != nil {
		t.Fatalf("InitForTest: %v", err)
	}
	defer func() { _ = providers.Shutdown(context.Background()) }()

	tracer := providers.TracerProvider.Tracer("test")
	mux := http.NewServeMux()
	mux.Handle("/v1/chat/completions", telemetry.SpanMiddleware(tracer)(
		http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusNotImplemented)
		}),
	))

	handler := reqidMiddleware(mux)
	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", strings.NewReader(`{}`))
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	spans := exporter.GetSpans()
	if len(spans) != 1 {
		t.Fatalf("expected 1 span, got %d", len(spans))
	}
	span := spans[0]
	if span.Name != "POST /v1/chat/completions" {
		t.Fatalf("span name %q", span.Name)
	}
	if got := attrString(span.Attributes, "http.method"); got != "POST" {
		t.Fatalf("http.method = %q", got)
	}
	if got := attrString(span.Attributes, "http.route"); got != "/v1/chat/completions" {
		t.Fatalf("http.route = %q", got)
	}
	if got := attrInt(span.Attributes, "http.status_code"); got != int64(http.StatusNotImplemented) {
		t.Fatalf("http.status_code = %d", got)
	}
	if _, ok := attrStringOK(span.Attributes, "ibex.request_id"); !ok {
		t.Fatal("missing ibex.request_id")
	}
}

func TestSpanMiddleware_ErrorSpan(t *testing.T) {
	exporter := tracetest.NewInMemoryExporter()
	providers, err := telemetry.InitForTest(exporter)
	if err != nil {
		t.Fatalf("InitForTest: %v", err)
	}
	defer func() { _ = providers.Shutdown(context.Background()) }()

	tracer := providers.TracerProvider.Tracer("test")
	handler := telemetry.SpanMiddleware(tracer)(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))

	req := httptest.NewRequest(http.MethodGet, "/error", nil)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	spans := exporter.GetSpans()
	if len(spans) != 1 {
		t.Fatalf("expected 1 span, got %d", len(spans))
	}
	if spans[0].Status.Code != codes.Error {
		t.Fatalf("expected ERROR status, got %v", spans[0].Status.Code)
	}
}
