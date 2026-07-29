package http

import (
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/packages/ratelimit"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/google/uuid"
)

func serveRateLimitProbe(t *testing.T, limiter ratelimit.Limiter, req *http.Request) *httptest.ResponseRecorder {
	t.Helper()
	handler := RateLimitMiddleware(limiter, logger.Discard("proxy"), metrics.NewProxy("test"))(
		http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) { w.WriteHeader(http.StatusOK) }),
	)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)
	return rec
}

type rateLimitProbeOpts struct {
	withAuth bool
	orgID    uuid.UUID
}

func rateLimitProbeRequest(opts rateLimitProbeOpts) *http.Request {
	req := httptest.NewRequest(http.MethodGet, "/v1/internal/auth-probe", nil)
	if !opts.withAuth {
		return req
	}
	return req.WithContext(auth.WithContext(req.Context(), &auth.ValidateResult{OrgID: opts.orgID}))
}

func TestRateLimitMiddleware_errorPaths(t *testing.T) {
	t.Parallel()
	orgID := uuid.MustParse("550e8400-e29b-41d4-a716-446655440000")

	cases := []struct {
		name       string
		limiter    ratelimit.Limiter
		opts       rateLimitProbeOpts
		wantStatus int
	}{
		{
			name: "missing auth context", limiter: &mockLimiter{},
			wantStatus: http.StatusInternalServerError,
		},
		{
			name: "invalid org id", limiter: &mockLimiter{},
			opts:       rateLimitProbeOpts{withAuth: true, orgID: uuid.Nil},
			wantStatus: http.StatusInternalServerError,
		},
		{
			name: "fail open", limiter: &mockLimiter{err: errors.New("redis down")},
			opts: rateLimitProbeOpts{withAuth: true, orgID: orgID}, wantStatus: http.StatusOK,
		},
	}

	for _, tc := range cases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			rec := serveRateLimitProbe(t, tc.limiter, rateLimitProbeRequest(tc.opts))
			if rec.Code != tc.wantStatus {
				t.Fatalf("status: %d body=%s", rec.Code, rec.Body.String())
			}
		})
	}
}
