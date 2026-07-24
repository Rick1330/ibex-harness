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

func (s *stubDirectiveResolver) Invalidate(uuid.UUID, uuid.UUID) {}

func TestDirectiveResolveMiddleware_SetsContext(t *testing.T) {
	orgID := uuid.MustParse("550e8400-e29b-41d4-a716-446655440001")
	agentID := uuid.MustParse("550e8400-e29b-41d4-a716-446655440000")
	want := directive.Resolved{Content: "Be helpful.", InjectionMode: "system_first"}

	handler := DirectiveResolveMiddleware(&stubDirectiveResolver{resolved: want}, logger.Discard("proxy"))(
		http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			got, ok := ResolvedDirectiveFromContext(r.Context())
			if !ok {
				http.Error(w, "missing directive", http.StatusInternalServerError)
				return
			}
			if got.Content != want.Content {
				http.Error(w, "wrong content", http.StatusInternalServerError)
				return
			}
			w.WriteHeader(http.StatusOK)
		}),
	)

	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", nil)
	req = req.WithContext(WithAgent(req.Context(), auth.AgentRecord{ID: agentID, OrgID: orgID, Status: "active"}))
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("status=%d body=%q", rec.Code, rec.Body.String())
	}
}

func TestDirectiveResolveMiddleware_FailOpenOnError(t *testing.T) {
	orgID := uuid.MustParse("550e8400-e29b-41d4-a716-446655440001")
	agentID := uuid.MustParse("550e8400-e29b-41d4-a716-446655440000")

	handler := DirectiveResolveMiddleware(
		&stubDirectiveResolver{err: errors.New("postgres down")},
		logger.Discard("proxy"),
	)(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if _, ok := ResolvedDirectiveFromContext(r.Context()); ok {
			http.Error(w, "unexpected directive", http.StatusInternalServerError)
			return
		}
		w.WriteHeader(http.StatusOK)
	}))

	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", nil)
	req = req.WithContext(WithAgent(req.Context(), auth.AgentRecord{ID: agentID, OrgID: orgID, Status: "active"}))
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("status=%d want fail-open 200", rec.Code)
	}
}

func TestDirectiveResolveMiddleware_SkipsWithoutAgent(t *testing.T) {
	handler := DirectiveResolveMiddleware(
		&stubDirectiveResolver{resolved: directive.Resolved{Content: "should not run"}},
		logger.Discard("proxy"),
	)(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if _, ok := ResolvedDirectiveFromContext(r.Context()); ok {
			http.Error(w, "unexpected directive", http.StatusInternalServerError)
			return
		}
		w.WriteHeader(http.StatusOK)
	}))

	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", nil)
	handler.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("status=%d", rec.Code)
	}
}
