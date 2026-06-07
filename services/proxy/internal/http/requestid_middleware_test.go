package http

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/reqid"
	"github.com/Rick1330/ibex-harness/packages/telemetry"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/config"
	proxyerrors "github.com/Rick1330/ibex-harness/services/proxy/internal/errors"
	"github.com/google/uuid"
)

func requestIDHandlerChain(cfg config.Config) http.Handler {
	tracer := telemetry.NoopTracer("test")
	return RequestContextMiddleware(cfg)(
		telemetry.SpanMiddleware(tracer)(
			ResponseHeadersMiddleware(cfg)(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				w.WriteHeader(http.StatusOK)
			})),
		),
	)
}

func TestRequestContextMiddleware_generatesV7(t *testing.T) {
	cfg := config.Config{RequestIDHeader: "X-Request-ID", TraceIDHeader: "X-Trace-ID"}
	rec := httptest.NewRecorder()
	requestIDHandlerChain(cfg).ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/", nil))

	header := rec.Header().Get("X-Request-ID")
	parsed, err := uuid.Parse(header)
	if err != nil {
		t.Fatalf("parse header: %v", err)
	}
	if parsed.Version() != 7 {
		t.Fatalf("version: %d want 7", parsed.Version())
	}
}

func TestRequestContextMiddleware_honoursValidV4(t *testing.T) {
	inbound := uuid.New().String()
	cfg := config.Config{RequestIDHeader: "X-Request-ID", TraceIDHeader: "X-Trace-ID"}
	req := httptest.NewRequest(http.MethodGet, "/", nil)
	req.Header.Set("X-Request-ID", inbound)
	rec := httptest.NewRecorder()
	requestIDHandlerChain(cfg).ServeHTTP(rec, req)

	if got := rec.Header().Get("X-Request-ID"); got != inbound {
		t.Fatalf("header: %q want %q", got, inbound)
	}
}

func TestRequestContextMiddleware_rejectsInvalidInbound(t *testing.T) {
	const garbage = "not-a-valid-uuid"
	cfg := config.Config{RequestIDHeader: "X-Request-ID", TraceIDHeader: "X-Trace-ID"}
	req := httptest.NewRequest(http.MethodGet, "/", nil)
	req.Header.Set("X-Request-ID", garbage)
	rec := httptest.NewRecorder()
	requestIDHandlerChain(cfg).ServeHTTP(rec, req)

	got := rec.Header().Get("X-Request-ID")
	if got == garbage {
		t.Fatal("garbage inbound ID was honoured")
	}
	parsed, err := uuid.Parse(got)
	if err != nil || parsed.Version() != 7 {
		t.Fatalf("expected fresh v7, got %q", got)
	}
}

func TestRequestContextMiddleware_contextPropagation(t *testing.T) {
	cfg := config.Config{RequestIDHeader: "X-Request-ID", TraceIDHeader: "X-Trace-ID"}
	handler := RequestContextMiddleware(cfg)(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		id, ok := reqid.FromContext(r.Context())
		if !ok || id == "" {
			t.Fatal("request id missing from context")
		}
		w.WriteHeader(http.StatusOK)
	}))
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/", nil))
	if rec.Code != http.StatusOK {
		t.Fatalf("status: %d", rec.Code)
	}
}

func TestRequestIDInErrorEnvelope_matchesHeader(t *testing.T) {
	cfg := config.Config{RequestIDHeader: "X-Request-ID", TraceIDHeader: "X-Trace-ID"}
	tracer := telemetry.NoopTracer("test")
	handler := RequestContextMiddleware(cfg)(
		telemetry.SpanMiddleware(tracer)(
			ResponseHeadersMiddleware(cfg)(
				ContentTypeMiddleware("")(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
					proxyerrors.Write(w, http.StatusBadRequest, proxyerrors.CodeValidationError,
						"fail", RequestIDFromContext(r.Context()), proxyerrors.WriteOpts{})
				})),
			),
		),
	)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, httptest.NewRequest(http.MethodPost, "/", strings.NewReader("{}")))
	if rec.Code != http.StatusUnsupportedMediaType {
		t.Fatalf("status: %d body=%s", rec.Code, rec.Body.String())
	}

	headerID := rec.Header().Get("X-Request-ID")
	if headerID == "" {
		t.Fatal("missing X-Request-ID header")
	}

	var body struct {
		Error struct {
			RequestID string `json:"request_id"`
		} `json:"error"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatal(err)
	}
	if body.Error.RequestID != headerID {
		t.Fatalf("request_id %q != header %q", body.Error.RequestID, headerID)
	}
}
