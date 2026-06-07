package http

import (
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/ratelimit"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/config"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/metrics"
)

func newTestRouter(cfg config.Config, validator auth.TokenValidator, limiter ratelimit.Limiter) http.Handler {
	return NewRouter(RouterDeps{
		Config:    cfg,
		Logger:    slog.New(slog.NewTextHandler(io.Discard, nil)),
		Metrics:   metrics.New(),
		Validator: validator,
		Limiter:   limiter,
	})
}

func TestHealthReturnsOK(t *testing.T) {
	router := newTestRouter(config.Config{ServiceName: "proxy"}, nil, nil)

	req := httptest.NewRequest(http.MethodGet, "/health", nil)
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", rec.Code)
	}
	if !strings.Contains(rec.Body.String(), `"status":"ok"`) {
		t.Fatalf("unexpected body: %s", rec.Body.String())
	}
}

func TestReadyMissingRedisURL(t *testing.T) {
	router := newTestRouter(config.Config{ServiceName: "proxy"}, nil, nil)

	req := httptest.NewRequest(http.MethodGet, "/ready", nil)
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, req)

	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected 503, got %d", rec.Code)
	}
	if !strings.Contains(rec.Body.String(), `"reason":"missing REDIS_URL"`) {
		t.Fatalf("unexpected body: %s", rec.Body.String())
	}
}
