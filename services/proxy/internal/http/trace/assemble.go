package trace

import (
	"time"

	ibexch "github.com/Rick1330/ibex-harness/packages/clickhouse"
	"github.com/Rick1330/ibex-harness/packages/provider"
)

// Assemble builds a TraceRecord with no prompt/completion content.
// Zero timestamps default to now/completed; negative durations and token
// counts clamp to zero and saturate at uint32 max so analytics stay bounded.
func Assemble(in AssembleInput) ibexch.TraceRecord {
	requested, completed := resolveTraceTimestamps(in.Timings)
	inTok, outTok, totalTok := usageTokenCounts(in.Usage)
	return ibexch.TraceRecord{
		RequestID:          in.RequestID,
		OrgID:              in.OrgID,
		AgentID:            in.AgentID,
		SessionID:          in.SessionID,
		CheckpointID:       in.CheckpointID,
		TraceID:            in.TraceID,
		RootSpanID:         in.RootSpanID,
		Model:              in.Model,
		Provider:           in.Provider,
		IsStreaming:        in.Streaming,
		InputTokens:        inTok,
		OutputTokens:       outTok,
		TotalTokens:        totalTok,
		AuthLatencyMs:      in.Timings.AuthMs,
		DirectiveLatencyMs: in.Timings.DirectiveMs,
		ProviderTTFBMs:     durationToUint32(in.Timings.ProviderTTFB),
		TotalLatencyMs:     durationToUint32(completed.Sub(requested)),
		StatusCode:         in.Outcome.StatusCode,
		IsComplete:         in.Outcome.IsComplete,
		ErrorCode:          in.Outcome.ErrorCode,
		RequestedAt:        requested,
		CompletedAt:        completed,
		OriginalModel:      optionalNonEmpty(in.OriginalModel),
		FallbackModel:      optionalNonEmpty(in.FallbackModel),
		FallbackReason:     in.FallbackReason,
		DirectiveVersionID: in.DirectiveVersionID,
		ContextAssemblyMs:  in.ContextAssemblyMs,
		ScoreSchema:        in.ScoreSchema,
		Completeness:       completenessOrDefault(in.Completeness),
	}
}

func resolveTraceTimestamps(t RequestTimings) (requested, completed time.Time) {
	completed = t.CompletedAt
	if completed.IsZero() {
		completed = time.Now().UTC()
	}
	requested = t.RequestedAt
	if requested.IsZero() {
		requested = completed
	}
	return requested.UTC(), completed.UTC()
}

func completenessOrDefault(v string) string {
	if v == "" {
		return "partial"
	}
	return v
}

func optionalNonEmpty(s string) *string {
	if s == "" {
		return nil
	}
	return &s
}

func usageTokenCounts(u *provider.Usage) (in, out, total uint32) {
	if u == nil {
		return 0, 0, 0
	}
	in = intToUint32(u.InputTokens)
	out = intToUint32(u.OutputTokens)
	total = intToUint32(u.TotalTokens)
	if total != 0 {
		return in, out, total
	}
	return in, out, addUint32Sat(in, out)
}

func addUint32Sat(a, b uint32) uint32 {
	sum := a + b
	if sum < a {
		return ^uint32(0)
	}
	return sum
}

func durationToUint32(d time.Duration) uint32 {
	if d <= 0 {
		return 0
	}
	ms := d / time.Millisecond
	if ms > time.Duration(^uint32(0)) {
		return ^uint32(0)
	}
	return uint32(ms)
}

func intToUint32(n int) uint32 {
	if n <= 0 {
		return 0
	}
	if n > int(^uint32(0)) {
		return ^uint32(0)
	}
	return uint32(n)
}
