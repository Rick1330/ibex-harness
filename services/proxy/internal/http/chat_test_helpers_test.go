package http

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/Rick1330/ibex-harness/infra/testing/httptestx"
	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/packages/permissions"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/packages/ratelimit"
	"github.com/Rick1330/ibex-harness/packages/responsepipeline"
	"github.com/Rick1330/ibex-harness/packages/telemetry"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/config"
	"github.com/google/uuid"
)

const testChatOrgID = "550e8400-e29b-41d4-a716-446655440001"
const testChatAgentID = "550e8400-e29b-41d4-a716-446655440000"

type chatMockValidator struct {
	res *auth.ValidateResult
	err error
}

func (m *chatMockValidator) Validate(_ context.Context, _ string) (*auth.ValidateResult, error) {
	return m.res, m.err
}

func chatTestConfig() config.Config {
	return config.Config{
		Environment: "test", ServiceName: "proxy", Port: "8080",
		MaxRequestBodyBytes: 1 << 20, RequestIDHeader: "X-Request-ID", TraceIDHeader: "X-Trace-ID",
	}
}

func defaultChatRouterDeps(tb testing.TB) RouterDeps {
	tb.Helper()
	return RouterDeps{
		Config:           chatTestConfig(),
		Logger:           logger.Discard("proxy"),
		Metrics:          metrics.NewProxy("test"),
		Tracer:           telemetry.NoopTracer("proxy"),
		Validator:        defaultChatValidator(),
		AgentVerifier:    passAgentVerifier{},
		Limiter:          ratelimit.Noop(),
		Health:           testHealthServer(),
		ProviderRegistry: mustEmptyProviderRegistry(tb),
		ResponsePipeline: responsepipeline.NewDefaultPipeline(),
	}
}

func mergeRouterDeps(base RouterDeps, overrides func(*RouterDeps)) RouterDeps {
	if overrides != nil {
		overrides(&base)
	}
	return base
}

func chatTestHandler(t *testing.T, validator auth.TokenValidator, cfg config.Config) http.Handler {
	t.Helper()
	return newTestRouter(t, cfg, validator, ratelimit.Noop())
}

type chatRequestOpts struct {
	method         string
	body           string
	contentType    string
	auth           bool
	agentID        string
	idempotencyKey string
}

func postChat(t *testing.T, handler http.Handler, opts chatRequestOpts) *httptest.ResponseRecorder {
	t.Helper()
	method := opts.method
	if method == "" {
		method = http.MethodPost
	}
	req := httptest.NewRequest(method, "/v1/chat/completions", httptestx.RequestBody(opts.body))
	httptestx.ApplyChatHeaders(req, httptestx.ChatHeaders{
		Auth: opts.auth, ContentType: opts.contentType, AgentID: opts.agentID, HasBody: opts.body != "",
	})
	if opts.idempotencyKey != "" {
		req.Header.Set("Idempotency-Key", opts.idempotencyKey)
	}
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)
	return rec
}

func defaultChatValidator() *chatMockValidator {
	return &chatMockValidator{res: &auth.ValidateResult{
		OrgID: uuid.MustParse(testChatOrgID), Permissions: permissions.ProxyChatCompletion,
	}}
}

func chatRouterWithProvider(t *testing.T, reg *provider.Registry, overrides func(*RouterDeps)) http.Handler {
	t.Helper()
	return mustNewRouter(t, mergeRouterDeps(defaultChatRouterDeps(t), func(d *RouterDeps) {
		if reg != nil {
			d.ProviderRegistry = reg
		}
		if overrides != nil {
			overrides(d)
		}
	}))
}
