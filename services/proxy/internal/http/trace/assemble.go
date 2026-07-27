package trace

import (
	"time"

	ibexch "github.com/Rick1330/ibex-harness/packages/clickhouse"
	"github.com/Rick1330/ibex-harness/packages/provider"
)

// Assemble builds a TraceRecord with no prompt/completion content.
func Assemble(in AssembleInput) ibexch.TraceRecord {
	completed := in.Timings.CompletedAt
	if completed.IsZero() {
		completed = time.Now().UTC()
	}
	requested := in.Timings.RequestedAt
	if requested.IsZero() {
		requested = completed
	}
	totalMs := durationToUint32(completed.Sub(requested))
	inTok, outTok, totalTok := usageTokenCounts(in.Usage)
	return ibexch.TraceRecord{
		RequestID:          in.RequestID,
		OrgID:              in.OrgID,
		AgentID:            in.AgentID,
		SessionID:          in.SessionID,
		CheckpointID:       nil, // AppendCheckpoint does not return IDs yet
		Model:              in.Model,
		Provider:           in.Provider,
		IsStreaming:        in.Streaming,
		InputTokens:        inTok,
		OutputTokens:       outTok,
		TotalTokens:        totalTok,
		AuthLatencyMs:      in.Timings.AuthMs,
		DirectiveLatencyMs: in.Timings.DirectiveMs,
		ProviderTTFBMs:     durationToUint32(in.Timings.ProviderTTFB),
		TotalLatencyMs:     totalMs,
		StatusCode:         in.Outcome.StatusCode,
		IsComplete:         in.Outcome.IsComplete,
		ErrorCode:          in.Outcome.ErrorCode,
		RequestedAt:        requested.UTC(),
		CompletedAt:        completed.UTC(),
	}
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
	return in, out, in + out
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
