package http

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/directive"
	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	httpsession "github.com/Rick1330/ibex-harness/services/proxy/internal/http/session"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/llm"
	"github.com/google/uuid"
)

func TestUnit_TenantIDsFromContext(t *testing.T) {
	t.Parallel()

	agentID := uuid.New()
	orgID := uuid.MustParse(testChatOrgID)

	cases := []struct {
		name    string
		ctx     func() context.Context
		wantOK  bool
		wantOrg uuid.UUID
		wantAgt uuid.UUID
	}{
		{
			name:   "missing agent",
			ctx:    func() context.Context { return context.Background() },
			wantOK: false,
		},
		{
			name: "missing auth",
			ctx: func() context.Context {
				return WithAgent(context.Background(), auth.AgentRecord{ID: agentID})
			},
			wantOK: false,
		},
		{
			name: "invalid org uuid",
			ctx: func() context.Context {
				ctx := WithAgent(context.Background(), auth.AgentRecord{ID: agentID})
				return auth.WithContext(ctx, &auth.ValidateResult{OrgID: "bad"})
			},
			wantOK: false,
		},
		{
			name: "valid tenant ids",
			ctx: func() context.Context {
				ctx := WithAgent(context.Background(), auth.AgentRecord{ID: agentID})
				return auth.WithContext(ctx, &auth.ValidateResult{OrgID: orgID.String()})
			},
			wantOK:  true,
			wantOrg: orgID,
			wantAgt: agentID,
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			gotOrg, gotAgt, ok := tenantIDsFromContext(tc.ctx())
			if ok != tc.wantOK {
				t.Fatalf("ok=%v want %v", ok, tc.wantOK)
			}
			if !tc.wantOK {
				return
			}
			if gotOrg != tc.wantOrg {
				t.Fatalf("org=%s want %s", gotOrg, tc.wantOrg)
			}
			if gotAgt != tc.wantAgt {
				t.Fatalf("agent=%s want %s", gotAgt, tc.wantAgt)
			}
		})
	}
}

func TestUnit_DirectiveVersionPtr(t *testing.T) {
	t.Parallel()

	vid := uuid.New()

	cases := []struct {
		name    string
		ctx     func() context.Context
		wantNil bool
	}{
		{
			name:    "no directive in context",
			ctx:     func() context.Context { return context.Background() },
			wantNil: true,
		},
		{
			name: "zero version id",
			ctx: func() context.Context {
				return WithResolvedDirective(context.Background(), directive.Resolved{VersionID: uuid.Nil})
			},
			wantNil: true,
		},
		{
			name: "non-zero version id",
			ctx: func() context.Context {
				return WithResolvedDirective(context.Background(), directive.Resolved{VersionID: vid})
			},
			wantNil: false,
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			got := directiveVersionPtr(tc.ctx())
			if tc.wantNil {
				if got != nil {
					t.Fatalf("expected nil, got %v", got)
				}
				return
			}
			if got == nil || *got != vid {
				t.Fatalf("got=%v want %s", got, vid)
			}
		})
	}
}

func TestUnit_DurableSessionID(t *testing.T) {
	t.Parallel()

	sid := uuid.New()

	cases := []struct {
		name   string
		ctx    func() context.Context
		wantOK bool
		wantID uuid.UUID
	}{
		{
			name:   "no session in context",
			ctx:    func() context.Context { return context.Background() },
			wantOK: false,
		},
		{
			name: "sticky-only session",
			ctx: func() context.Context {
				return withResolvedSession(context.Background(), httpsession.Resolved{ExternalID: "sticky"})
			},
			wantOK: false,
		},
		{
			name: "durable session",
			ctx: func() context.Context {
				return withResolvedSession(context.Background(), httpsession.Resolved{
					SessionID: sid, ExternalID: "e",
				})
			},
			wantOK: true,
			wantID: sid,
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			got, ok := durableSessionID(tc.ctx())
			if ok != tc.wantOK {
				t.Fatalf("ok=%v want %v", ok, tc.wantOK)
			}
			if tc.wantOK && got != tc.wantID {
				t.Fatalf("got=%s want %s", got, tc.wantID)
			}
		})
	}
}

func TestUnit_ResolveSession_MissingTenant(t *testing.T) {
	t.Parallel()

	h := chatCompletionHandler{
		log:          logger.Discard("proxy"),
		sessionStore: &memSessionStore{},
	}
	req := httptest.NewRequest(http.MethodPost, "/", nil)

	out := h.resolveSessionForRequest(req, &llm.ChatCompletionRequest{Model: "m"}, "openai")

	rs, ok := ResolvedSessionFromContext(out.Context())
	if !ok || rs.Durable() {
		t.Fatalf("expected sticky-only rs=%+v ok=%v", rs, ok)
	}
}
