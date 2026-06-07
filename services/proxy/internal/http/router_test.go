package http

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/packages/ratelimit"
	"github.com/Rick1330/ibex-harness/packages/telemetry"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/config"
	"github.com/google/uuid"
)

type passAgentVerifier struct{}

func (passAgentVerifier) Verify(_ context.Context, _, agentID, orgID string) (*auth.AgentRecord, error) {
	aid, err := uuid.Parse(agentID)
	if err != nil {
		return nil, auth.ErrAgentNotAuthorized
	}
	oid, err := uuid.Parse(orgID)
	if err != nil {
		return nil, auth.ErrAgentNotAuthorized
	}
	return &auth.AgentRecord{ID: aid, OrgID: oid, Status: "active"}, nil
}

func newTestRouter(cfg config.Config, validator auth.TokenValidator, limiter ratelimit.Limiter) http.Handler {
	var agentVerifier auth.AgentVerifier
	if validator != nil {
		agentVerifier = passAgentVerifier{}
	}
	return NewRouter(RouterDeps{
		Config:        cfg,
		Logger:        logger.Discard("proxy"),
		Metrics:       metrics.NewProxy("test"),
		Tracer:        telemetry.NoopTracer("proxy"),
		Validator:     validator,
		AgentVerifier: agentVerifier,
		Limiter:       limiter,
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
