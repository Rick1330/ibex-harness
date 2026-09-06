package http

import (
	"context"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/Rick1330/ibex-harness/packages/contextclient"
	"github.com/Rick1330/ibex-harness/packages/injection"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/packages/responsepipeline"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/validation"
)

// Header names for context-assembly outcome (3.5.D.2). Embedded ibex JSON is 3.5.D.3.
const (
	headerMemoriesInjected = "X-IBEX-Memories-Injected"
	headerContextTokens    = "X-IBEX-Context-Tokens"
	headerContextFallback  = "X-IBEX-Context-Fallback"
)

// contextAssembler is satisfied by *contextclient.Client; tests supply fakes.
type contextAssembler interface {
	Assemble(ctx context.Context, req contextclient.AssembleParams) contextclient.AssembleResult
}

// contextAssembleMeta records whether Assemble was attempted and its outcome.
// Attempted=false means Phase 2 only (flag off, nil client, or Skip-Memory) —
// response writers omit the three X-IBEX-Context-* headers so Phase 2 responses
// stay header-identical to pre-D.2 behavior. AssemblyMs is measured around the
// Assemble RPC for the embedded `ibex` block (3.5.D.3); unused for headers.
type contextAssembleMeta struct {
	Attempted        bool
	MemoriesInjected int32
	ContextTokens    int32
	Fallback         bool
	AssemblyMs       int64
}

type messageInjectionOutcome struct {
	Messages []provider.Message
	Meta     contextAssembleMeta
}

// applyContextOrDirectiveInjection chooses Assemble vs Phase 2 directive injection.
// Missing/disabled context, Skip-Memory, nil client, or an assembly Fallback leave
// messages with only directive injection applied — never blocks or degrades Complete.
func (h chatCompletionHandler) applyContextOrDirectiveInjection(
	ctx context.Context,
	r *http.Request,
	model string,
	messages []provider.Message,
) messageInjectionOutcome {
	if !h.shouldAssemble(r) {
		return messageInjectionOutcome{Messages: applyDirectiveInjection(ctx, messages)}
	}
	params, ok := assembleParamsFromRequest(ctx, model, messages)
	if !ok {
		return messageInjectionOutcome{Messages: applyDirectiveInjection(ctx, messages)}
	}
	assembleStart := time.Now()
	result := h.contextClient.Assemble(ctx, params)
	assemblyMs := time.Since(assembleStart).Milliseconds()
	meta := contextAssembleMeta{
		Attempted:        true,
		MemoriesInjected: result.MemoriesIncluded,
		ContextTokens:    result.TokensUsed,
		Fallback:         result.Fallback,
		AssemblyMs:       assemblyMs,
	}
	if result.Fallback || strings.TrimSpace(result.AssembledContext) == "" {
		// Empty assembled text is operationally a fallback: Phase 2 directive only.
		// Promote Fallback so headers/metrics match (D.1 client only records RPC Fallback).
		if !meta.Fallback {
			meta.Fallback = true
			h.recordAssembleFallback(emptyAssembleFallbackReason)
		}
		return messageInjectionOutcome{
			Messages: applyDirectiveInjection(ctx, messages),
			Meta:     meta,
		}
	}
	// AssembledContext already includes directive + memories (formatter ordering).
	// Inject as system_first so the blob is additive; leave client history intact.
	injected := injection.Inject(messages, result.AssembledContext, injection.ModeSystemFirst)
	return messageInjectionOutcome{Messages: injected, Meta: meta}
}

// emptyAssembleFallbackReason labels handler-side empty AssembledContext fail-open
// (distinct from gRPC status reasons recorded inside packages/contextclient).
const emptyAssembleFallbackReason = "empty"

func (h chatCompletionHandler) recordAssembleFallback(reason string) {
	if h.metrics == nil {
		return
	}
	h.metrics.IncContextAssembleFallback(reason)
}

func (h chatCompletionHandler) shouldAssemble(r *http.Request) bool {
	if !h.contextEnabled || h.contextClient == nil {
		return false
	}
	return !skipMemoryRequested(r.Header)
}

func skipMemoryRequested(h http.Header) bool {
	v := strings.TrimSpace(strings.ToLower(h.Get(validation.HeaderSkipMemory)))
	switch v {
	case "1", "true", "yes", "on":
		return true
	default:
		return false
	}
}

func assembleParamsFromRequest(ctx context.Context, model string, messages []provider.Message) (contextclient.AssembleParams, bool) {
	orgID, agentID, ok := tenantIDsFromContext(ctx)
	if !ok {
		return contextclient.AssembleParams{}, false
	}
	return contextclient.AssembleParams{
		OrgID:          orgID.String(),
		AgentID:        agentID.String(),
		Model:          model,
		Query:          lastUserQuery(messages),
		RecentMessages: toAssembleMessages(messages),
	}, true
}

func lastUserQuery(messages []provider.Message) string {
	for i := len(messages) - 1; i >= 0; i-- {
		if messages[i].Role == "user" {
			return messages[i].Content
		}
	}
	return ""
}

func toAssembleMessages(messages []provider.Message) []contextclient.Message {
	out := make([]contextclient.Message, len(messages))
	for i, m := range messages {
		out[i] = contextclient.Message{Role: m.Role, Content: m.Content}
	}
	return out
}

// setContextAssembleResponseHeaders writes the three D.2 headers when Assemble ran.
// Omitted entirely on the Phase 2 path (Attempted=false) for bit-identical headers.
func setContextAssembleResponseHeaders(w http.ResponseWriter, ctx context.Context) {
	meta, ok := contextAssembleMetaFromContext(ctx)
	if !ok || !meta.Attempted {
		return
	}
	w.Header().Set(headerMemoriesInjected, strconv.FormatInt(int64(meta.MemoriesInjected), 10))
	w.Header().Set(headerContextTokens, strconv.FormatInt(int64(meta.ContextTokens), 10))
	if meta.Fallback {
		w.Header().Set(headerContextFallback, "true")
		return
	}
	w.Header().Set(headerContextFallback, "false")
}

// attachIbexMetadataForPipeline copies D.2 assemble outcome + request timings into
// responsepipeline context for IBEXMetadataStage. No-op when Assemble was not
// attempted so the stage leaves Bytes() dirty=false (verbatim upstream body).
func attachIbexMetadataForPipeline(ctx context.Context) context.Context {
	meta, ok := contextAssembleMetaFromContext(ctx)
	if !ok || !meta.Attempted {
		return ctx
	}
	return responsepipeline.WithIbexMetadata(ctx, responsepipeline.IbexMetadata{
		TraceID:           traceIDFromContext(ctx),
		SessionID:         sessionIDForIbexMetadata(ctx),
		MemoriesInjected:  meta.MemoriesInjected,
		ContextTokensUsed: meta.ContextTokens,
		ContextAssemblyMs: meta.AssemblyMs,
		ProxyOverheadMs:   proxyOverheadMs(ctx),
	})
}

func sessionIDForIbexMetadata(ctx context.Context) string {
	if id, ok := durableSessionID(ctx); ok {
		return id.String()
	}
	rs, ok := ResolvedSessionFromContext(ctx)
	if !ok {
		return ""
	}
	return rs.ExternalID
}

// proxyOverheadMs is wall time since request start minus provider Complete duration
// (auth + assemble + pipeline + write prep). Matches MONITORING.md proxy_overhead_ms.
func proxyOverheadMs(ctx context.Context) int64 {
	start, ok := RequestStartFromContext(ctx)
	if !ok {
		return 0
	}
	total := time.Since(start).Milliseconds()
	if providerMs, ok := providerDurationMsFromContext(ctx); ok {
		overhead := total - providerMs
		if overhead < 0 {
			return 0
		}
		return overhead
	}
	return total
}
