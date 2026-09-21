package billing

import (
	"context"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"
)

type usageFactValidateCase struct {
	name string
	mut  func(UsageFact) UsageFact
	want string
}

func newValidateWriter(t *testing.T) *UsageFactWriter {
	t.Helper()
	w := NewUsageFactWriterWithInserter(&fakeUsageFactInserter{}, UsageFactConfig{
		MaxBatchSize: 10, MaxBufferSize: 100, FlushInterval: time.Hour,
	})
	t.Cleanup(func() { _ = w.Shutdown(context.Background()) })
	return w
}

func identityValidateCases() []usageFactValidateCase {
	return []usageFactValidateCase{
		{name: "empty request id", mut: func(f UsageFact) UsageFact { f.RequestID = ""; return f }, want: "missing required ids"},
		{name: "nil org", mut: func(f UsageFact) UsageFact { f.OrgID = uuid.Nil; return f }, want: "missing required ids"},
		{name: "nil agent", mut: func(f UsageFact) UsageFact { f.AgentID = uuid.Nil; return f }, want: "missing required ids"},
		{name: "request id too long", mut: func(f UsageFact) UsageFact { f.RequestID = strings.Repeat("r", maxRequestIDLen+1); return f }, want: "request_id too long"},
		{name: "zero occurred_at", mut: func(f UsageFact) UsageFact { f.OccurredAt = time.Time{}; return f }, want: "missing occurred_at"},
	}
}

func modelValidateCases() []usageFactValidateCase {
	longModel := strings.Repeat("m", maxModelLen+1)
	return []usageFactValidateCase{
		{name: "empty provider", mut: func(f UsageFact) UsageFact { f.Provider = ""; return f }, want: "provider and model are required"},
		{name: "empty model", mut: func(f UsageFact) UsageFact { f.Model = ""; return f }, want: "provider and model are required"},
		{name: "provider too long", mut: func(f UsageFact) UsageFact { f.Provider = strings.Repeat("p", maxProviderLen+1); return f }, want: "provider or model exceeds max length"},
		{name: "model too long", mut: func(f UsageFact) UsageFact { f.Model = longModel; return f }, want: "provider or model exceeds max length"},
		{name: "fallback reason too long", mut: func(f UsageFact) UsageFact { f.FallbackReason = strings.Repeat("x", maxFallbackReasonLen+1); return f }, want: "fallback_reason too long"},
		{name: "original model too long", mut: func(f UsageFact) UsageFact { s := longModel; f.OriginalModel = &s; return f }, want: "original_model too long"},
		{name: "fallback model too long", mut: func(f UsageFact) UsageFact { s := longModel; f.FallbackModel = &s; return f }, want: "fallback_model too long"},
		{name: "empty rate card version", mut: func(f UsageFact) UsageFact { f.RateCardVersion = ""; return f }, want: "missing or invalid rate_card_version"},
		{name: "rate card version too long", mut: func(f UsageFact) UsageFact { f.RateCardVersion = strings.Repeat("v", maxRateCardVerLen+1); return f }, want: "missing or invalid rate_card_version"},
	}
}

func tokenValidateCases() []usageFactValidateCase {
	return []usageFactValidateCase{
		{name: "invalid completeness", mut: func(f UsageFact) UsageFact { f.Completeness = "nope"; return f }, want: "invalid completeness"},
		{name: "token sum overflow", mut: func(f UsageFact) UsageFact {
			f.InputTokens = ^uint32(0)
			f.OutputTokens = 1
			f.TotalTokens = 0
			return f
		}, want: "token sum overflow"},
		{name: "total mismatch", mut: func(f UsageFact) UsageFact { f.TotalTokens = 1; return f }, want: "total_tokens must equal input+output"},
		{name: "negative cost", mut: func(f UsageFact) UsageFact { f.EstimatedCostCents = -1; return f }, want: "estimated_cost_cents must be non-negative"},
	}
}

func TestUsageFactWriter_ValidateFailures(t *testing.T) {
	t.Parallel()
	cases := append(append(identityValidateCases(), modelValidateCases()...), tokenValidateCases()...)
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			w := newValidateWriter(t)
			err := w.Write(tc.mut(validUsageFact()))
			if err == nil || !strings.Contains(err.Error(), tc.want) {
				t.Fatalf("err=%v want substring %q", err, tc.want)
			}
		})
	}
}
