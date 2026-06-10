package http

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/healthcheck"
	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/packages/telemetry"
)

func testHealthServer() *healthcheck.Server {
	return &healthcheck.Server{
		CriticalCheckers: map[string]healthcheck.Checker{
			"postgres": healthcheck.PostgresSelect1(nil),
			"grpc":     healthcheck.TCPReachable("127.0.0.1:1"),
		},
	}
}

func TestHealthReturnsOK(t *testing.T) {
	t.Parallel()
	router := NewRouter(logger.Discard("auth"), metrics.NewAuth(metrics.AuthConfig{ServiceName: "test"}), telemetry.NoopTracer("auth"), testHealthServer())

	req := httptest.NewRequest(http.MethodGet, "/health", nil)
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", rec.Code)
	}
	if !strings.Contains(rec.Body.String(), `"status":"ok"`) {
		t.Fatalf("unexpected body: %s", rec.Body.String())
	}
	if !strings.Contains(rec.Body.String(), `"checks":{}`) {
		t.Fatalf("expected empty checks: %s", rec.Body.String())
	}
}

func TestReadyPostgresNotConfigured(t *testing.T) {
	t.Parallel()
	router := NewRouter(logger.Discard("auth"), metrics.NewAuth(metrics.AuthConfig{ServiceName: "test"}), telemetry.NoopTracer("auth"), testHealthServer())

	req := httptest.NewRequest(http.MethodGet, "/ready", nil)
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, req)

	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected 503, got %d", rec.Code)
	}
	var body healthcheck.Response
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if body.Status != "unhealthy" {
		t.Fatalf("expected unhealthy, got %s", body.Status)
	}
	if body.Checks["postgres"].Status != "failed" {
		t.Fatalf("unexpected postgres check: %+v", body.Checks["postgres"])
	}
}
