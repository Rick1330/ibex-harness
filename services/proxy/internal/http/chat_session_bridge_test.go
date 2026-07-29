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

	t.Run("missing agent", func(t *testing.T) {
		t.Parallel()
		_, _, ok := tenantIDsFromContext(context.Background())
		if ok {
			t.Fatal("expected miss")
		}
	})

	t.Run("missing auth", func(t *testing.T) {
		t.Parallel()
		ctx := WithAgent(context.Background(), auth.AgentRecord{ID: uuid.New()})
		_, _, ok := tenantIDsFromContext(ctx)
		if ok {
			t.Fatal("expected miss")
		}
	})

	t.Run("bad org uuid", func(t *testing.T) {
		t.Parallel()
		ctx := WithAgent(context.Background(), auth.AgentRecord{ID: uuid.New()})
		ctx = auth.WithContext(ctx, &auth.ValidateResult{OrgID: "bad"})
		_, _, ok := tenantIDsFromContext(ctx)
		if ok {
			t.Fatal("expected miss")
		}
	})

	t.Run("ok", func(t *testing.T) {
		t.Parallel()
		agentID := uuid.New()
		orgID := uuid.MustParse(testChatOrgID)
		ctx := WithAgent(context.Background(), auth.AgentRecord{ID: agentID})
		ctx = auth.WithContext(ctx, &auth.ValidateResult{OrgID: orgID.String()})
		gotOrg, gotAgent, ok := tenantIDsFromContext(ctx)
		if !ok {
			t.Fatal("expected ok")
		}
		if gotOrg != orgID || gotAgent != agentID {
			t.Fatalf("org=%s agent=%s", gotOrg, gotAgent)
		}
	})
}

func TestUnit_DirectiveVersionPtr(t *testing.T) {
	t.Parallel()

	if directiveVersionPtr(context.Background()) != nil {
		t.Fatal("expected nil without directive")
	}

	ctx := WithResolvedDirective(context.Background(), directive.Resolved{VersionID: uuid.Nil})
	if directiveVersionPtr(ctx) != nil {
		t.Fatal("expected nil for zero version")
	}

	vid := uuid.New()
	ctx = WithResolvedDirective(context.Background(), directive.Resolved{VersionID: vid})
	got := directiveVersionPtr(ctx)
	if got == nil || *got != vid {
		t.Fatalf("got=%v want %s", got, vid)
	}
}

func TestUnit_DurableSessionID(t *testing.T) {
	t.Parallel()

	if _, ok := durableSessionID(context.Background()); ok {
		t.Fatal("expected miss")
	}

	sticky := httpsession.Resolved{ExternalID: "sticky"}
	ctx := withResolvedSession(context.Background(), sticky)
	if _, ok := durableSessionID(ctx); ok {
		t.Fatal("expected sticky miss")
	}

	sid := uuid.New()
	ctx = withResolvedSession(context.Background(), httpsession.Resolved{
		SessionID: sid, ExternalID: "e",
	})
	got, ok := durableSessionID(ctx)
	if !ok || got != sid {
		t.Fatalf("got=%s ok=%v", got, ok)
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
