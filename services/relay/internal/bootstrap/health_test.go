package bootstrap

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"

	"github.com/DATA-DOG/go-sqlmock"
	ibexmetrics "github.com/Rick1330/ibex-harness/packages/metrics"
)

func TestClickHousePingChecker(t *testing.T) {
	if err := clickHousePingChecker(nil)(t.Context()); err == nil {
		t.Fatal("nil runtime must fail the clickhouse check")
	}
	if err := clickHousePingChecker(&runtime{})(t.Context()); err == nil {
		t.Fatal("missing sink must fail the clickhouse check")
	}
	if err := clickHousePingChecker(&runtime{sink: newTestSink(t)})(t.Context()); err != nil {
		t.Fatalf("healthy sink: %v", err)
	}
}

func TestDrainingChecker(t *testing.T) {
	var draining atomic.Bool
	checker := drainingChecker(&draining)
	if err := checker(t.Context()); err != nil {
		t.Fatalf("healthy: %v", err)
	}
	draining.Store(true)
	if err := checker(t.Context()); err == nil {
		t.Fatal("draining must fail readiness")
	}
}

func TestRelayHTTPServer_Routes(t *testing.T) {
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = db.Close() })
	mock.MatchExpectationsInOrder(false)

	reg := ibexmetrics.NewRelay("test-relay")
	var draining atomic.Bool
	server := newRelayHTTPServer("0", &runtime{db: db}, reg, &draining)

	rec := httptest.NewRecorder()
	server.Handler.ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/health", nil))
	if rec.Code != http.StatusOK {
		t.Fatalf("/health: got %d", rec.Code)
	}

	rec = httptest.NewRecorder()
	server.Handler.ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/metrics", nil))
	if rec.Code != http.StatusOK || !strings.Contains(rec.Body.String(), "ibex_relay_claimed_total") {
		t.Fatalf("/metrics: code=%d body=%s", rec.Code, rec.Body.String())
	}

	draining.Store(true)
	rec = httptest.NewRecorder()
	server.Handler.ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/ready", nil))
	if rec.Code != http.StatusServiceUnavailable || !strings.Contains(rec.Body.String(), "shutdown in progress") {
		t.Fatalf("/ready while draining: code=%d body=%s", rec.Code, rec.Body.String())
	}
}
