package http

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/billing"
	"github.com/Rick1330/ibex-harness/packages/directive"
	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/provider"
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
			name: "zero org uuid",
			ctx: func() context.Context {
				ctx := WithAgent(context.Background(), auth.AgentRecord{ID: agentID})
				return auth.WithContext(ctx, &auth.ValidateResult{OrgID: uuid.Nil})
			},
			wantOK: false,
		},
		{
			name: "valid tenant ids",
			ctx: func() context.Context {
				ctx := WithAgent(context.Background(), auth.AgentRecord{ID: agentID})
				return auth.WithContext(ctx, &auth.ValidateResult{OrgID: orgID})
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

func TestUnit_UsageCompleteness(t *testing.T) {
	t.Parallel()
	cases := []struct {
		name string
		in   checkpointInput
		want string
	}{
		{name: "nil usage incomplete", in: checkpointInput{IsComplete: true}, want: "partial"},
		{name: "usage incomplete", in: checkpointInput{Usage: &provider.Usage{}, IsComplete: false}, want: "partial"},
		{name: "complete", in: checkpointInput{Usage: &provider.Usage{}, IsComplete: true}, want: "complete"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			if got := usageCompleteness(tc.in); got != tc.want {
				t.Fatalf("got=%q want %q", got, tc.want)
			}
		})
	}
}

func TestUnit_ClampUint32Tokens(t *testing.T) {
	t.Parallel()
	cases := []struct {
		name string
		n    int64
		want uint32
	}{
		{name: "zero", n: 0, want: 0},
		{name: "negative", n: -1, want: 0},
		{name: "normal", n: 42, want: 42},
		{name: "overflow", n: int64(^uint32(0)) + 1, want: ^uint32(0)},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			if got := clampUint32Tokens(tc.n); got != tc.want {
				t.Fatalf("got=%d want %d", got, tc.want)
			}
		})
	}
}

func TestUnit_OptionalStringPtr(t *testing.T) {
	t.Parallel()
	if got := optionalStringPtr(""); got != nil {
		t.Fatalf("empty: got %v", got)
	}
	got := optionalStringPtr("x")
	if got == nil || *got != "x" {
		t.Fatalf("got=%v want x", got)
	}
}

func TestUnit_EstimateCostChecked(t *testing.T) {
	t.Parallel()
	card := billing.CardVersion{
		Version: "3",
		Prices: []billing.PriceRow{{
			Provider: "openai", ModelPattern: "gpt-4o*",
			InputCentsPer1k: 250, OutputCentsPer1k: 1000,
		}},
	}
	cents, ver, ok := estimateCostChecked(card, "openai", "gpt-4o-mini", 1, 1)
	if !ok || ver != "3" || cents != 2 {
		t.Fatalf("ok=%v cents=%d ver=%s", ok, cents, ver)
	}
	if _, _, ok := estimateCostChecked(billing.CardVersion{Version: "1"}, "x", "y", 1, 1); ok {
		t.Fatal("expected fail for empty prices")
	}
}

func TestUnit_ResolvePublishedCard(t *testing.T) {
	t.Parallel()

	got := resolvePublishedCard(context.Background(), nil, uuid.New())
	if got.Version != "0" || got.Prices != nil {
		t.Fatalf("nil cache: got=%+v", got)
	}

	org := uuid.New()
	published := billing.CardVersion{
		Version: "9",
		Prices: []billing.PriceRow{{
			Provider: "openai", ModelPattern: "gpt-4o*",
			InputCentsPer1k: 100, OutputCentsPer1k: 200,
		}},
	}
	cache, err := billing.NewCache(stubBudgetLoader{
		snap: billing.BudgetSnapshot{PublishedCard: published},
	}, billing.Config{CacheTTL: time.Minute, LRUSize: 4}, billing.NoopMetrics{})
	if err != nil {
		t.Fatal(err)
	}
	got = resolvePublishedCard(context.Background(), cache, org)
	if got.Version != "9" || len(got.Prices) != 1 {
		t.Fatalf("published: got=%+v", got)
	}
}

func TestUnit_BuildFrozenUsageFact(t *testing.T) {
	t.Parallel()

	org := uuid.New()
	agent := uuid.New()
	published := billing.CardVersion{
		Version: "5",
		Prices: []billing.PriceRow{{
			Provider: "openai", ModelPattern: "gpt-4o*",
			InputCentsPer1k: 250, OutputCentsPer1k: 1000,
		}},
	}
	cache, err := billing.NewCache(stubBudgetLoader{
		snap: billing.BudgetSnapshot{PublishedCard: published},
	}, billing.Config{CacheTTL: time.Minute, LRUSize: 4}, billing.NoopMetrics{})
	if err != nil {
		t.Fatal(err)
	}

	t.Run("matching price", func(t *testing.T) {
		t.Parallel()
		fixed := time.Date(2024, 6, 1, 12, 0, 0, 0, time.UTC)
		fact := buildFrozenUsageFact(context.Background(), freezeUsageFactInput{
			meta: httpsession.SnapshotMeta{
				RequestID: "req-1", OrgID: org, AgentID: agent, RequestedAt: fixed,
			},
			in: checkpointInput{
				Provider: "openai", Model: "gpt-4o-mini",
				Usage: &provider.Usage{InputTokens: 1, OutputTokens: 1}, IsComplete: true,
			},
			budgetCache: cache,
		})
		if fact == nil {
			t.Fatal("expected fact")
		}
		if fact.EstimatedCostCents != 2 || fact.RateCardVersion != "5" {
			t.Fatalf("cents=%d ver=%s", fact.EstimatedCostCents, fact.RateCardVersion)
		}
		if fact.Completeness != "complete" {
			t.Fatalf("completeness=%s", fact.Completeness)
		}
		if !fact.OccurredAt.Equal(fixed) {
			t.Fatalf("occurred=%v want %v", fact.OccurredAt, fixed)
		}
	})

	t.Run("estimate fails empty prices", func(t *testing.T) {
		t.Parallel()
		emptyCache, err := billing.NewCache(stubBudgetLoader{
			snap: billing.BudgetSnapshot{PublishedCard: billing.CardVersion{Version: "1"}},
		}, billing.Config{CacheTTL: time.Minute, LRUSize: 4}, billing.NoopMetrics{})
		if err != nil {
			t.Fatal(err)
		}
		fact := buildFrozenUsageFact(context.Background(), freezeUsageFactInput{
			meta: httpsession.SnapshotMeta{OrgID: org, AgentID: agent},
			in: checkpointInput{
				Provider: "openai", Model: "gpt-4o",
				Usage: &provider.Usage{InputTokens: 1, OutputTokens: 1}, IsComplete: true,
			},
			budgetCache: emptyCache,
		})
		if fact != nil {
			t.Fatalf("expected nil, got %+v", fact)
		}
	})

	t.Run("partial completeness", func(t *testing.T) {
		t.Parallel()
		fact := buildFrozenUsageFact(context.Background(), freezeUsageFactInput{
			meta: httpsession.SnapshotMeta{OrgID: org, AgentID: agent, RequestedAt: time.Now().UTC()},
			in: checkpointInput{
				Provider: "openai", Model: "gpt-4o-mini",
				Usage: &provider.Usage{InputTokens: 1, OutputTokens: 1}, IsComplete: false,
			},
			budgetCache: cache,
		})
		if fact == nil || fact.Completeness != "partial" {
			t.Fatalf("got=%+v", fact)
		}
	})

	t.Run("zero requested at sets time", func(t *testing.T) {
		t.Parallel()
		before := time.Now().UTC().Add(-time.Second)
		fact := buildFrozenUsageFact(context.Background(), freezeUsageFactInput{
			meta: httpsession.SnapshotMeta{OrgID: org, AgentID: agent},
			in: checkpointInput{
				Provider: "openai", Model: "gpt-4o-mini",
				Usage: &provider.Usage{InputTokens: 1, OutputTokens: 1}, IsComplete: true,
			},
			budgetCache: cache,
		})
		after := time.Now().UTC().Add(time.Second)
		if fact == nil {
			t.Fatal("expected fact")
		}
		if fact.OccurredAt.Before(before) || fact.OccurredAt.After(after) {
			t.Fatalf("occurred=%v not in [%v,%v]", fact.OccurredAt, before, after)
		}
	})
}
