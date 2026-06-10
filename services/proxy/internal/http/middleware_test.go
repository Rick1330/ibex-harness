package http

import (
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	apierror "github.com/Rick1330/ibex-harness/packages/apierror"
	"github.com/Rick1330/ibex-harness/packages/telemetry"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/config"
)

func TestBodySizeLimitMiddleware_rejectsOversizedContentLength(t *testing.T) {
	handler := BodySizeLimitMiddleware(10, "")(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	req := httptest.NewRequest(http.MethodPost, "/", strings.NewReader("small"))
	req.ContentLength = 100
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)
	if rec.Code != http.StatusRequestEntityTooLarge {
		t.Fatalf("status: %d", rec.Code)
	}
	if !strings.Contains(rec.Body.String(), string(apierror.CodePayloadTooLarge)) {
		t.Fatalf("body: %s", rec.Body.String())
	}
}

func TestContentTypeMiddleware_requiresJSON(t *testing.T) {
	handler := chain(
		RequestContextMiddleware(config.Config{RequestIDHeader: "X-Request-ID", TraceIDHeader: "X-Trace-ID"}),
		ContentTypeMiddleware(""),
	)(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	req := httptest.NewRequest(http.MethodPost, "/", nil)
	req.Header.Set("Content-Type", "text/plain")
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)
	if rec.Code != http.StatusUnsupportedMediaType {
		t.Fatalf("status: %d body=%s", rec.Code, rec.Body.String())
	}
}

func TestResponseHeadersMiddleware_setsHeaders(t *testing.T) {
	cfg := config.Config{RequestIDHeader: "X-Request-ID", TraceIDHeader: "X-Trace-ID"}
	tracer := telemetry.NoopTracer("test")
	handler := RequestContextMiddleware(cfg)(
		telemetry.SpanMiddleware(tracer)(
			ResponseHeadersMiddleware(cfg)(
				http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
					w.WriteHeader(http.StatusOK)
				}),
			),
		),
	)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/", nil))
	if rec.Header().Get("X-Request-ID") == "" {
		t.Fatal("missing X-Request-ID")
	}
	if rec.Header().Get("X-Trace-ID") == "" {
		t.Fatal("missing X-Trace-ID")
	}
	if rec.Header().Get("X-Response-Time") == "" {
		t.Fatal("missing X-Response-Time")
	}
}

func TestBodySizeLimitMiddleware_enforcesOnRead(t *testing.T) {
	handler := chain(
		RequestContextMiddleware(config.Config{RequestIDHeader: "X-Request-ID", TraceIDHeader: "X-Trace-ID"}),
		BodySizeLimitMiddleware(5, ""),
	)(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, err := io.ReadAll(r.Body)
		if IsMaxBytesError(err) {
			apierror.WriteStatus(w, http.StatusRequestEntityTooLarge, apierror.CodePayloadTooLarge,
				"Request body too large", RequestIDFromContext(r.Context()), apierror.WriteOpts{})
			return
		}
		w.WriteHeader(http.StatusOK)
	}))
	body := strings.Repeat("x", 20)
	req := httptest.NewRequest(http.MethodPost, "/", strings.NewReader(body))
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)
	if rec.Code != http.StatusRequestEntityTooLarge {
		t.Fatalf("status: %d", rec.Code)
	}
}
