package http

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/directive"
	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/google/uuid"
)

type stubDirectiveResolver struct {
	resolved directive.Resolved
	err      error
}

func (s *stubDirectiveResolver) Resolve(context.Context, uuid.UUID, uuid.UUID) (directive.Resolved, error) {
	return s.resolved, s.err
}

func (s *stubDirectiveResolver) Invalidate(context.Context, uuid.UUID, uuid.UUID) {
	// No-op stub.
}

type directiveMWCase struct {
	name        string
	withAgent   bool
	resolver    *stubDirectiveResolver
	wantStatus  int
	wantCtx     bool
	wantContent string
}

func TestUnit_DirectiveResolveMiddleware(t *testing.T) {
	t.Parallel()

	orgID := uuid.MustParse("550e8400-e29b-41d4-a716-446655440001")
	agentID := uuid.MustParse("550e8400-e29b-41d4-a716-446655440000")
	want := directive.Resolved{Content: "Be helpful.", InjectionMode: "system_first"}

	cases := []directiveMWCase{
		{
			name: "sets_context", withAgent: true,
			resolver:   &stubDirectiveResolver{resolved: want},
			wantStatus: http.StatusOK, wantCtx: true, wantContent: want.Content,
		},
		{
			name: "fail_open_on_error", withAgent: true,
			resolver:   &stubDirectiveResolver{err: errors.New("postgres down")},
			wantStatus: http.StatusOK, wantCtx: false,
		},
		{
			name: "skips_without_agent", withAgent: false,
			resolver:   &stubDirectiveResolver{resolved: directive.Resolved{Content: "should not run"}},
			wantStatus: http.StatusOK, wantCtx: false,
		},
	}
	for _, tc := range cases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			runDirectiveMWCase(t, tc, orgID, agentID)
		})
	}
}

func runDirectiveMWCase(t *testing.T, tc directiveMWCase, orgID, agentID uuid.UUID) {
	t.Helper()
	handler := DirectiveResolveMiddleware(tc.resolver, logger.Discard("proxy"))(
		http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			assertDirectiveContext(w, r, tc)
		}),
	)

	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", nil)
	if tc.withAgent {
		req = req.WithContext(WithAgent(req.Context(), auth.AgentRecord{
			ID: agentID, OrgID: orgID, Status: "active",
		}))
	}
	handler.ServeHTTP(rec, req)
	if rec.Code != tc.wantStatus {
		t.Fatalf("status=%d body=%q", rec.Code, rec.Body.String())
	}
}

func assertDirectiveContext(w http.ResponseWriter, r *http.Request, tc directiveMWCase) {
	got, ok := ResolvedDirectiveFromContext(r.Context())
	if tc.wantCtx {
		if !ok || got.Content != tc.wantContent {
			http.Error(w, "missing or wrong directive", http.StatusInternalServerError)
			return
		}
		w.WriteHeader(http.StatusOK)
		return
	}
	if ok {
		http.Error(w, "unexpected directive", http.StatusInternalServerError)
		return
	}
	w.WriteHeader(http.StatusOK)
}
