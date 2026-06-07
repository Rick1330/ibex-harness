package http

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/telemetry"

	"github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/services/auth/internal/config"
)

func TestHealthReturnsOK(t *testing.T) {
	router := NewRouter(config.Config{ServiceName: "auth"}, logger.Discard("auth"), metrics.NewAuth(metrics.AuthConfig{ServiceName: "test"}), telemetry.NoopTracer("auth"))

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

func TestReadyMissingPostgresDSN(t *testing.T) {
	router := NewRouter(config.Config{ServiceName: "auth"}, logger.Discard("auth"), metrics.NewAuth(metrics.AuthConfig{ServiceName: "test"}), telemetry.NoopTracer("auth"))

	req := httptest.NewRequest(http.MethodGet, "/ready", nil)
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, req)

	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected 503, got %d", rec.Code)
	}
	if !strings.Contains(rec.Body.String(), `"reason":"missing POSTGRES_DSN"`) {
		t.Fatalf("unexpected body: %s", rec.Body.String())
	}
}
