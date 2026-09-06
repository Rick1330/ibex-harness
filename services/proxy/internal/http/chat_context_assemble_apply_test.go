package http

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/contextclient"
	"github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/validation"
	dto "github.com/prometheus/client_model/go"
)

func TestUnit_ApplyContextOrDirective_DisabledNoAssembleCall(t *testing.T) {
	t.Parallel()
	fake := &fakeContextAssembler{result: contextclient.AssembleResult{AssembledContext: "should-not-inject"}}
	out := runApplyInjection(t, contextHandler(false, fake), []provider.Message{{Role: "user", Content: "hi"}})
	if fake.calls.Load() != 0 {
		t.Fatalf("Assemble calls=%d want 0", fake.calls.Load())
	}
	assertDirectiveOnly(t, out.Messages)
	if out.Meta.Attempted {
		t.Fatal("Attempted should be false when disabled")
	}
}

func TestUnit_ApplyContextOrDirective_NilClientNoAssembleCall(t *testing.T) {
	t.Parallel()
	out := runApplyInjection(t, contextHandler(true, nil), []provider.Message{{Role: "user", Content: "hi"}})
	if out.Meta.Attempted {
		t.Fatal("Attempted should be false when client nil")
	}
	assertDirectiveOnly(t, out.Messages)
}

func TestUnit_ApplyContextOrDirective_SkipMemoryNoAssembleCall(t *testing.T) {
	t.Parallel()
	fake := &fakeContextAssembler{result: contextclient.AssembleResult{AssembledContext: "assembled"}}
	h := contextHandler(true, fake)
	ctx := directiveCtx(contextTestAuthCtx(t))
	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", nil).WithContext(ctx)
	req.Header.Set(validation.HeaderSkipMemory, "true")
	assertNoAssembleAttempt(t, h, fake, ctx, req, "Skip-Memory")
}

func TestUnit_ApplyContextOrDirective_MissingTenantFallsBackToDirective(t *testing.T) {
	t.Parallel()
	fake := &fakeContextAssembler{result: contextclient.AssembleResult{AssembledContext: "assembled"}}
	h := contextHandler(true, fake)
	ctx := directiveCtx(context.Background())
	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", nil).WithContext(ctx)
	out := assertNoAssembleAttempt(t, h, fake, ctx, req, "tenant IDs missing")
	assertDirectiveOnly(t, out.Messages)
}

// assertNoAssembleAttempt checks Skip-Memory / missing-tenant style gates: no RPC, Attempted=false.
func assertNoAssembleAttempt(
	t *testing.T,
	h chatCompletionHandler,
	fake *fakeContextAssembler,
	ctx context.Context,
	req *http.Request,
	reason string,
) messageInjectionOutcome {
	t.Helper()
	out := h.applyContextOrDirectiveInjection(ctx, req, "gpt-4o", []provider.Message{{Role: "user", Content: "hi"}})
	if fake.calls.Load() != 0 {
		t.Fatalf("Assemble calls=%d want 0 (%s)", fake.calls.Load(), reason)
	}
	if out.Meta.Attempted {
		t.Fatalf("Attempted should be false when %s", reason)
	}
	return out
}

func TestUnit_ApplyContextOrDirective_FallbackKeepsDirective(t *testing.T) {
	t.Parallel()
	fake := &fakeContextAssembler{result: contextclient.AssembleResult{
		Fallback: true, FallbackReason: "DeadlineExceeded",
	}}
	out := runApplyInjection(t, contextHandler(true, fake), []provider.Message{{Role: "user", Content: "hi"}})
	if fake.calls.Load() != 1 {
		t.Fatalf("Assemble calls=%d want 1", fake.calls.Load())
	}
	if !out.Meta.Attempted {
		t.Fatalf("meta=%+v", out.Meta)
	}
	if !out.Meta.Fallback {
		t.Fatalf("meta=%+v", out.Meta)
	}
	assertDirectiveOnly(t, out.Messages)
}

func TestUnit_ApplyContextOrDirective_SuccessInjectsAdditive(t *testing.T) {
	t.Parallel()
	fake := &fakeContextAssembler{result: contextclient.AssembleResult{
		AssembledContext: "assembled blob", TokensUsed: 42, MemoriesIncluded: 3,
	}}
	msgs := []provider.Message{
		{Role: "system", Content: "client system"},
		{Role: "user", Content: "hello"},
	}
	out := runApplyInjection(t, contextHandler(true, fake), msgs)
	assertAssembleCallOnce(t, fake)
	assertAssembleParams(t, fake.lastReq)
	assertAssembledMessages(t, out.Messages)
	assertAssembleMeta(t, out.Meta)
}

func assertAssembleCallOnce(t *testing.T, fake *fakeContextAssembler) {
	t.Helper()
	if fake.calls.Load() != 1 {
		t.Fatalf("Assemble calls=%d", fake.calls.Load())
	}
}

func assertAssembleParams(t *testing.T, got contextclient.AssembleParams) {
	t.Helper()
	if got.Query != "hello" {
		t.Fatalf("query=%q", got.Query)
	}
	if got.OrgID != testChatOrgID {
		t.Fatalf("org=%q", got.OrgID)
	}
}

func assertAssembledMessages(t *testing.T, msgs []provider.Message) {
	t.Helper()
	if len(msgs) != 3 {
		t.Fatalf("messages=%+v", msgs)
	}
	if msgs[0].Content != "assembled blob" {
		t.Fatalf("first=%+v", msgs[0])
	}
	if msgs[1].Content != "client system" {
		t.Fatalf("system=%+v", msgs[1])
	}
	if msgs[2].Content != "hello" {
		t.Fatalf("user=%+v", msgs[2])
	}
}

func assertAssembleMeta(t *testing.T, meta contextAssembleMeta) {
	t.Helper()
	if meta.MemoriesInjected != 3 {
		t.Fatalf("memories=%d", meta.MemoriesInjected)
	}
	if meta.ContextTokens != 42 {
		t.Fatalf("tokens=%d", meta.ContextTokens)
	}
	if meta.Fallback {
		t.Fatal("unexpected Fallback")
	}
}

func TestUnit_SetContextAssembleResponseHeaders_OmitWhenNotAttempted(t *testing.T) {
	t.Parallel()
	rec := httptest.NewRecorder()
	setContextAssembleResponseHeaders(rec, context.Background())
	assertNoContextHeaders(t, rec.Header())
	ctx := withContextAssembleMeta(context.Background(), contextAssembleMeta{})
	setContextAssembleResponseHeaders(rec, ctx)
	assertNoContextHeaders(t, rec.Header())
}

func TestUnit_AssembleParamsFromRequest_MissingTenant(t *testing.T) {
	t.Parallel()
	_, ok := assembleParamsFromRequest(context.Background(), "gpt-4o", nil)
	if ok {
		t.Fatal("expected ok=false without tenant context")
	}
}

func TestUnit_LastUserQuery_EmptyWhenNoUser(t *testing.T) {
	t.Parallel()
	if got := lastUserQuery([]provider.Message{{Role: "system", Content: "sys"}}); got != "" {
		t.Fatalf("got %q want empty", got)
	}
}

func TestUnit_ApplyContextOrDirective_EmptyAssembledUsesDirective(t *testing.T) {
	t.Parallel()
	fake := &fakeContextAssembler{result: contextclient.AssembleResult{
		AssembledContext: "   ", TokensUsed: 1,
	}}
	reg := metrics.NewProxy("empty-assemble-test")
	h := contextHandler(true, fake)
	h.metrics = reg
	out := runApplyInjection(t, h, []provider.Message{{Role: "user", Content: "hi"}})
	if !out.Meta.Attempted {
		t.Fatalf("meta=%+v", out.Meta)
	}
	if !out.Meta.Fallback {
		t.Fatalf("empty AssembledContext must set Fallback=true, meta=%+v", out.Meta)
	}
	assertDirectiveOnly(t, out.Messages)
	assertAssembleFallbackMetric(t, reg, emptyAssembleFallbackReason, 1)
}

func assertAssembleFallbackMetric(t *testing.T, reg *metrics.ProxyRegistry, reason string, want float64) {
	t.Helper()
	got := assembleFallbackCounterValue(t, reg, reason)
	if got != want {
		t.Fatalf("fallback metric reason=%q got=%v want=%v", reason, got, want)
	}
}

func assembleFallbackCounterValue(t *testing.T, reg *metrics.ProxyRegistry, reason string) float64 {
	t.Helper()
	mfs, err := reg.Gatherer().Gather()
	if err != nil {
		t.Fatalf("gather: %v", err)
	}
	return counterValueForReasonLabel(mfs, "ibex_proxy_context_assemble_fallback_total", reason)
}

func counterValueForReasonLabel(mfs []*dto.MetricFamily, name, reason string) float64 {
	for _, mf := range mfs {
		if mf.GetName() != name {
			continue
		}
		if v, ok := counterWithReason(mf.GetMetric(), reason); ok {
			return v
		}
	}
	return 0
}

func counterWithReason(samples []*dto.Metric, reason string) (float64, bool) {
	for _, m := range samples {
		if metricHasLabelValue(m, "reason", reason) {
			return m.GetCounter().GetValue(), true
		}
	}
	return 0, false
}

func metricHasLabelValue(m *dto.Metric, name, value string) bool {
	for _, lp := range m.GetLabel() {
		if lp.GetName() == name && lp.GetValue() == value {
			return true
		}
	}
	return false
}
