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

func TestUnit_EstimateCostChecked_Match(t *testing.T) {
	t.Parallel()
	card := billing.CardVersion{
		Version: "3",
		Prices: []billing.PriceRow{{
			Provider: "openai", ModelPattern: "gpt-4o*",
			InputCentsPer1k: 250, OutputCentsPer1k: 1000,
		}},
	}
	cents, ver, ok := estimateCostChecked(estimateCostInput{
		card: card, provider: "openai", model: "gpt-4o-mini", inTok: 1, outTok: 1,
	})
	if !ok {
		t.Fatal("expected ok")
	}
	if ver != "3" {
		t.Fatalf("ver=%s", ver)
	}
	if cents != 2 {
		t.Fatalf("cents=%d", cents)
	}
}

func TestUnit_EstimateCostChecked_NoMatch(t *testing.T) {
	t.Parallel()
	_, _, ok := estimateCostChecked(estimateCostInput{
		card: billing.CardVersion{Version: "1"}, provider: "x", model: "y", inTok: 1, outTok: 1,
	})
	if ok {
		t.Fatal("expected fail for empty prices")
	}
}

func TestUnit_ResolvePublishedCard_NilCache(t *testing.T) {
	t.Parallel()
	got := resolvePublishedCard(context.Background(), nil, uuid.New())
	if got.Version != "0" {
		t.Fatalf("version=%s", got.Version)
	}
	if got.Prices != nil {
		t.Fatalf("prices=%v", got.Prices)
	}
}

func TestUnit_ResolvePublishedCard_FromCache(t *testing.T) {
	t.Parallel()
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
	got := resolvePublishedCard(context.Background(), cache, org)
	if got.Version != "9" {
		t.Fatalf("version=%s", got.Version)
	}
	if len(got.Prices) != 1 {
		t.Fatalf("prices=%d", len(got.Prices))
	}
}

func TestUnit_BuildFrozenUsageFact_MatchingPrice(t *testing.T) {
	t.Parallel()
	org, agent, cache := frozenUsageFactFixture(t)
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
	assertFrozenFact(t, fact, frozenFactWant{cents: 2, ver: "5", completeness: "complete", occurred: fixed})
}

func TestUnit_BuildFrozenUsageFact_EstimateFails(t *testing.T) {
	t.Parallel()
	org, agent, _ := frozenUsageFactFixture(t)
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
}

func TestUnit_BuildFrozenUsageFact_PartialCompleteness(t *testing.T) {
	t.Parallel()
	org, agent, cache := frozenUsageFactFixture(t)
	fact := buildFrozenUsageFact(context.Background(), freezeUsageFactInput{
		meta: httpsession.SnapshotMeta{OrgID: org, AgentID: agent, RequestedAt: time.Now().UTC()},
		in: checkpointInput{
			Provider: "openai", Model: "gpt-4o-mini",
			Usage: &provider.Usage{InputTokens: 1, OutputTokens: 1}, IsComplete: false,
		},
		budgetCache: cache,
	})
	if fact == nil {
		t.Fatal("expected fact")
	}
	if fact.Completeness != "partial" {
		t.Fatalf("completeness=%s", fact.Completeness)
	}
}

func TestUnit_BuildFrozenUsageFact_ZeroRequestedAt(t *testing.T) {
	t.Parallel()
	org, agent, cache := frozenUsageFactFixture(t)
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
	if fact.OccurredAt.Before(before) {
		t.Fatalf("occurred=%v before %v", fact.OccurredAt, before)
	}
	if fact.OccurredAt.After(after) {
		t.Fatalf("occurred=%v after %v", fact.OccurredAt, after)
	}
}

func frozenUsageFactFixture(t *testing.T) (uuid.UUID, uuid.UUID, *billing.Cache) {
	t.Helper()
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
	return org, agent, cache
}

type frozenFactWant struct {
	cents        int64
	ver          string
	completeness string
	occurred     time.Time
}

func assertFrozenFact(t *testing.T, fact *billing.UsageFact, want frozenFactWant) {
	t.Helper()
	if fact == nil {
		t.Fatal("expected fact")
	}
	if fact.EstimatedCostCents != want.cents {
		t.Fatalf("cents=%d want %d", fact.EstimatedCostCents, want.cents)
	}
	if fact.RateCardVersion != want.ver {
		t.Fatalf("ver=%s want %s", fact.RateCardVersion, want.ver)
	}
	if fact.Completeness != want.completeness {
		t.Fatalf("completeness=%s", fact.Completeness)
	}
	if !fact.OccurredAt.Equal(want.occurred) {
		t.Fatalf("occurred=%v want %v", fact.OccurredAt, want.occurred)
	}
}

func TestUnit_MetaHasTenantIDs(t *testing.T) {
	t.Parallel()
	org, agent := uuid.New(), uuid.New()
	cases := []struct {
		name string
		meta httpsession.SnapshotMeta
		want bool
	}{
		{name: "both valid", meta: httpsession.SnapshotMeta{OrgID: org, AgentID: agent}, want: true},
		{name: "nil org", meta: httpsession.SnapshotMeta{AgentID: agent}, want: false},
		{name: "nil agent", meta: httpsession.SnapshotMeta{OrgID: org}, want: false},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			if got := metaHasTenantIDs(tc.meta); got != tc.want {
				t.Fatalf("got %v want %v", got, tc.want)
			}
		})
	}
}

func TestUnit_CanFreezeUsageFact_NilWriter(t *testing.T) {
	t.Parallel()
	meta := httpsession.SnapshotMeta{OrgID: uuid.New(), AgentID: uuid.New()}
	if canFreezeUsageFact(nil, meta) {
		t.Fatal("nil writer must not freeze")
	}
}

func TestUnit_ResolvePublishedCard_CacheErrorDefaults(t *testing.T) {
	t.Parallel()
	cache, err := billing.NewCache(stubBudgetLoader{
		err: context.DeadlineExceeded,
	}, billing.Config{CacheTTL: time.Minute, LRUSize: 4}, billing.NoopMetrics{})
	if err != nil {
		t.Fatal(err)
	}
	got := resolvePublishedCard(context.Background(), cache, uuid.New())
	if got.Version != "0" {
		t.Fatalf("version=%s", got.Version)
	}
}

func TestUnit_ResolvePublishedCard_EmptyVersionDefaults(t *testing.T) {
	t.Parallel()
	cache, err := billing.NewCache(stubBudgetLoader{
		snap: billing.BudgetSnapshot{PublishedCard: billing.CardVersion{Version: ""}},
	}, billing.Config{CacheTTL: time.Minute, LRUSize: 4}, billing.NoopMetrics{})
	if err != nil {
		t.Fatal(err)
	}
	got := resolvePublishedCard(context.Background(), cache, uuid.New())
	if got.Version != "0" {
		t.Fatalf("version=%s", got.Version)
	}
}

func TestUnit_TokenCounts_NilUsage(t *testing.T) {
	t.Parallel()
	in, out := tokenCounts(checkpointInput{})
	if in != 0 || out != 0 {
		t.Fatalf("got %d/%d", in, out)
	}
}

func TestUnit_SafeAddInt64_OverflowClamps(t *testing.T) {
	t.Parallel()
	got := safeAddInt64(1<<62, 1<<62)
	if got != 1<<63-1 {
		t.Fatalf("got %d", got)
	}
}

func TestUnit_SetSessionResponseHeader_SetsWhenResolved(t *testing.T) {
	t.Parallel()
	ctx := withResolvedSession(context.Background(), httpsession.Resolved{ExternalID: "ext-1"})
	rec := httptest.NewRecorder()
	setSessionResponseHeader(rec, ctx)
	if got := rec.Header().Get(httpsession.HeaderSessionID); got != "ext-1" {
		t.Fatalf("header=%q", got)
	}
}

func TestUnit_SetSessionResponseHeader_NoopWithoutResolved(t *testing.T) {
	t.Parallel()
	rec := httptest.NewRecorder()
	setSessionResponseHeader(rec, context.Background())
	if got := rec.Header().Get(httpsession.HeaderSessionID); got != "" {
		t.Fatalf("unexpected header %q", got)
	}
}
