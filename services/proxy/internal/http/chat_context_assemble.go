package http

import (
	"context"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/Rick1330/ibex-harness/packages/contextclient"
	"github.com/Rick1330/ibex-harness/packages/evidenceoutbox"
	"github.com/Rick1330/ibex-harness/packages/injection"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/packages/responsepipeline"
	httpsession "github.com/Rick1330/ibex-harness/services/proxy/internal/http/session"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/validation"
	"github.com/google/uuid"
	"go.opentelemetry.io/otel"
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

// proxyOverheadRecorder records one completed non-streaming request's enforcement
// overhead on the `assembly` series that matches whether context assembly ran for
// it. It is satisfied by *metrics.ProxyRegistry; a nil recorder is a no-op.
type proxyOverheadRecorder interface {
	ObserveNonStreamingProxyOverhead(assemblyEnabled bool, seconds float64)
}

// contextAssembleMeta records whether Assemble was attempted and its outcome.
// Attempted=false means Phase 2 only (flag off, nil client, Skip-Memory, or a
// request too incomplete to assemble) — response writers omit the three
// X-IBEX-Context-* headers so Phase 2 responses stay header-identical to pre-D.2
// behavior. AssemblyMs is measured around the Assemble RPC for the embedded
// `ibex` block (3.5.D.3); unused for headers. Attempted is also the `assembly`
// metric label: it is true whenever the RPC ran, including a fail-open result,
// because a failed assembly still spends its wall time inside this request's
// overhead and the ratified population is "context assembly disabled".
// overhead is the handler's recorder, carried here because the metadata write
// happens in a context-only helper that no longer has the handler in scope.
type contextAssembleMeta struct {
	Attempted        bool
	MemoriesInjected int32
	ContextTokens    int32
	Fallback         bool
	AssemblyMs       int64
	ScoreSchema      string
	EvidenceExtras   httpsession.EvidenceExtras
	overhead         proxyOverheadRecorder
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
		return h.phase2Outcome(ctx, messages)
	}
	assembleCtx, endSpan := ensureAssembleTraceContext(ctx)
	defer endSpan()
	if _, ok := PrincipalContextFromContext(assembleCtx); !ok {
		// The context server rejects a request without a verified principal
		// (UNAUTHENTICATED). Skip the RPC and stay on the directive-only path with
		// no fallback metadata rather than send a call that cannot succeed. The
		// skip is security-relevant, so it is counted with a bounded reason; the
		// response-header contract is unchanged (Attempted stays false).
		h.warnMissingPrincipal(ctx)
		h.recordAssembleFallback(principalMissingFallbackReason)
		return h.phase2Outcome(ctx, messages)
	}
	params, ok := assembleParamsFromRequest(assembleCtx, model, messages)
	if !ok {
		return h.phase2Outcome(ctx, messages)
	}
	return h.injectAssembledOrDirective(ctx, assembleCtx, messages, params)
}

// phase2Outcome is the directive-only outcome used whenever Assemble is skipped.
// Attempted stays false, so the response headers stay identical to pre-D.2
// behavior, but the recorder travels with it: a request that never assembles
// context still contributes a proxy-overhead sample, labelled assembly=disabled,
// to the ratified SLO population.
func (h chatCompletionHandler) phase2Outcome(ctx context.Context, messages []provider.Message) messageInjectionOutcome {
	return messageInjectionOutcome{
		Messages: applyDirectiveInjection(ctx, messages),
		Meta:     contextAssembleMeta{overhead: h.enforcementRecorder()},
	}
}

// enforcementRecorder narrows h.metrics to the recorder the metadata write
// needs, or returns nil when metrics are not wired (tests). The explicit nil
// check keeps a typed-nil *metrics.ProxyRegistry out of the interface.
func (h chatCompletionHandler) enforcementRecorder() proxyOverheadRecorder {
	if h.metrics == nil {
		return nil
	}
	return h.metrics
}

// warnMissingPrincipal logs the skipped assemble once per request.
func (h chatCompletionHandler) warnMissingPrincipal(ctx context.Context) {
	if h.log == nil {
		return
	}
	h.log.WarnCtx(ctx, "context assemble skipped; verified principal context unavailable")
}

func (h chatCompletionHandler) injectAssembledOrDirective(
	ctx, assembleCtx context.Context,
	messages []provider.Message,
	params contextclient.AssembleParams,
) messageInjectionOutcome {
	assembleStart := time.Now()
	result := h.contextClient.Assemble(assembleCtx, params)
	assembleElapsed := time.Since(assembleStart)
	h.observeContextAssemble(assembleElapsed)
	extras := evidenceExtrasFromAssemble(result)
	extras.AssembleSpanID = spanIDFromContext(assembleCtx)
	meta := contextAssembleMeta{
		Attempted:        true,
		MemoriesInjected: result.MemoriesIncluded,
		ContextTokens:    result.TokensUsed,
		Fallback:         result.Fallback,
		AssemblyMs:       assembleElapsed.Milliseconds(),
		ScoreSchema:      result.ScoreSchema,
		EvidenceExtras:   extras,
		overhead:         h.enforcementRecorder(),
	}
	if result.Fallback || strings.TrimSpace(result.AssembledContext) == "" {
		if !meta.Fallback {
			meta.Fallback = true
			h.recordAssembleFallback(emptyAssembleFallbackReason)
		}
		return messageInjectionOutcome{
			Messages: applyDirectiveInjection(ctx, messages),
			Meta:     meta,
		}
	}
	injected := injection.Inject(messages, result.AssembledContext, injection.ModeSystemFirst)
	return messageInjectionOutcome{Messages: injected, Meta: meta}
}

// observeContextAssemble records the Assemble RPC wall time. Fail-open results
// are included on purpose: a timed-out or empty assemble is exactly what the
// context-assembly SLO panel has to show, and this is the only place the proxy
// sees that latency.
func (h chatCompletionHandler) observeContextAssemble(elapsed time.Duration) {
	if h.metrics == nil {
		return
	}
	h.metrics.ObserveContextAssembleSeconds(elapsed.Seconds())
}

func ensureAssembleTraceContext(ctx context.Context) (context.Context, func()) {
	// Always start a child assemble span so evidence/join keys use a real OTel
	// span_id (never a synthetic root+".assemble" id).
	tracer := otel.Tracer("github.com/Rick1330/ibex-harness/services/proxy/internal/http")
	ctx, span := tracer.Start(ctx, "chatCompletionHandler.AssembleContext")
	return ctx, func() { span.End() }
}

func evidenceExtrasFromAssemble(result contextclient.AssembleResult) httpsession.EvidenceExtras {
	extras := httpsession.EvidenceExtras{
		Metrics: assemblyMetricsFromClient(result.Metrics),
	}
	schema := result.ScoreSchema
	if schema == "" {
		schema = evidenceoutbox.ScoreSchemaInterim
	}
	extras.Candidates = scoreCandidatesFromMemories(result.MemoriesUsed, schema)
	return extras
}

func assemblyMetricsFromClient(m *contextclient.AssemblyMetrics) *evidenceoutbox.AssemblyMetrics {
	if m == nil {
		return nil
	}
	return &evidenceoutbox.AssemblyMetrics{
		BudgetCalculationMs:   int(m.BudgetCalculationMs),
		DirectiveLoadMs:       int(m.DirectiveLoadMs),
		HotMemoryRetrievalMs:  int(m.HotMemoryRetrievalMs),
		ColdMemoryRetrievalMs: int(m.ColdMemoryRetrievalMs),
		RankingMs:             int(m.RankingMs),
		PackingMs:             int(m.PackingMs),
		FormattingMs:          int(m.FormattingMs),
		TotalMs:               int(m.TotalMs),
		CandidatesEvaluated:   int(m.CandidatesEvaluated),
	}
}

func scoreCandidatesFromMemories(memories []contextclient.MemoryUsed, schema string) []evidenceoutbox.ScoreCandidate {
	out := make([]evidenceoutbox.ScoreCandidate, 0, len(memories))
	finalRank := 0
	for _, m := range memories {
		id, err := uuid.Parse(m.MemoryID)
		if err != nil {
			continue
		}
		excl := m.Exclusion
		if excl == "" {
			excl = "included"
		}
		out = append(out, scoreCandidateFromMemory(scoreCandidateInput{
			id: id, mem: m, exclusion: excl, schema: schema, finalRank: &finalRank,
		}))
	}
	return out
}

type scoreCandidateInput struct {
	id        uuid.UUID
	mem       contextclient.MemoryUsed
	exclusion string
	schema    string
	finalRank *int
}

func scoreCandidateFromMemory(in scoreCandidateInput) evidenceoutbox.ScoreCandidate {
	rank := int(in.mem.Rank)
	sim := float64(in.mem.Similarity)
	conf := float64(in.mem.Confidence)
	comp := float64(in.mem.CompositeScore)
	tok := int(in.mem.TokenEstimate)
	var packedRank *int
	if in.exclusion == "included" {
		*in.finalRank++
		r := *in.finalRank
		packedRank = &r
	}
	return evidenceoutbox.ScoreCandidate{
		MemoryID:       in.id,
		RetrievalRank:  rank,
		FinalRank:      packedRank,
		Similarity:     &sim,
		Confidence:     &conf,
		CompositeScore: &comp,
		ScoreSchema:    in.schema,
		ScoreComponents: map[string]float64{
			"similarity": sim,
			"confidence": conf,
		},
		Exclusion:     in.exclusion,
		TokenEstimate: &tok,
		Category:      in.mem.Category,
	}
}

func finalRankForExclusion(exclusion string, rank int) *int {
	if exclusion != "" && exclusion != "included" {
		return nil
	}
	r := rank
	return &r
}

// emptyAssembleFallbackReason labels handler-side empty AssembledContext fail-open
// (distinct from gRPC status reasons recorded inside packages/contextclient).
const emptyAssembleFallbackReason = "empty"

// principalMissingFallbackReason labels the handler-side skip of Assemble when no
// verified principal is bound to the request. Bounded label: the reason is a
// constant, so it cannot grow metric cardinality.
const principalMissingFallbackReason = "principal_missing"

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
	return validation.SkipMemoryRequested(h)
}

func assembleParamsFromRequest(ctx context.Context, model string, messages []provider.Message) (contextclient.AssembleParams, bool) {
	orgID, agentID, ok := tenantIDsFromContext(ctx)
	if !ok {
		return contextclient.AssembleParams{}, false
	}
	var sessionID string
	if id, ok := durableSessionID(ctx); ok {
		sessionID = id.String()
	}
	var directiveVersionID string
	if id := directiveVersionPtr(ctx); id != nil {
		directiveVersionID = id.String()
	}
	traceID := traceIDFromContext(ctx)
	spanID := spanIDFromContext(ctx)
	if traceID == "" || spanID == "" {
		return contextclient.AssembleParams{}, false
	}
	principal, ok := PrincipalContextFromContext(ctx)
	if !ok {
		return contextclient.AssembleParams{}, false
	}
	return contextclient.AssembleParams{
		OrgID:              orgID.String(),
		AgentID:            agentID.String(),
		SessionID:          sessionID,
		Model:              model,
		Query:              lastUserQuery(messages),
		DirectiveVersionID: directiveVersionID,
		RequestID:          RequestIDFromContext(ctx),
		TraceID:            traceID,
		SpanID:             spanID,
		PrincipalContext:   principal,
		RecentMessages:     toAssembleMessages(messages),
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
//
// The proxy_overhead_ms it embeds is measured here, before the pipeline runs and
// before the body is serialized: it is a diagnostic number for the response body
// and cannot include work that has not happened yet. The SLO sample is a
// different, larger measurement — finishProxyOverheadObservation takes it after
// Run and Bytes — so the two are deliberately not the same value, and the
// histogram is the authoritative one.
func attachIbexMetadataForPipeline(ctx context.Context) context.Context {
	meta, ok := contextAssembleMetaFromContext(ctx)
	if !ok {
		return ctx
	}
	if !meta.Attempted {
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

// finishProxyOverheadObservation records one completed non-streaming request:
// the ibex_proxy_overhead_seconds sample and the matching
// ibex_proxy_nonstreaming_requests_total increment, on the `assembly` series the
// request belongs to. Call it after the response pipeline has run and the
// processed body has been serialized, so the sample covers stage work and JSON
// serialization instead of only the pre-pipeline prefix.
//
// It is called once per request by contract: encodePipelineResult runs once per
// response, and the streaming path never reaches it, which is what keeps the
// population "completed non-streaming requests". A missing assemble metadata
// value or an unwired recorder make it a no-op.
func finishProxyOverheadObservation(ctx context.Context) {
	observeProxyOverheadAt(ctx, time.Now())
}

// observeProxyOverheadAt is finishProxyOverheadObservation with an injected
// clock. The 20 ms bucket boundary decides the SLO, so its tests pin the sample
// exactly instead of racing time.Since against the assertion.
//
// The population label is meta.Attempted: assembly=enabled means the Assemble
// RPC ran and its wall time is part of this sample, so the request is not in the
// ratified "context assembly disabled" population. A fail-open assembly counts
// as enabled for that reason — the RPC ran even though nothing was injected.
func observeProxyOverheadAt(ctx context.Context, now time.Time) {
	meta, ok := contextAssembleMetaFromContext(ctx)
	if !ok || meta.overhead == nil {
		return
	}
	overhead, ok := proxyOverheadDuration(ctx, now)
	if !ok {
		return
	}
	meta.overhead.ObserveNonStreamingProxyOverhead(meta.Attempted, overhead.Seconds())
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

// proxyOverheadDuration is wall time since request start minus provider Complete
// time, clamped at zero (auth + assemble + pipeline + serialization).
//
// Both terms keep full time.Duration precision. Rounding the result to whole
// milliseconds first would turn a 20.4 ms overhead into 20 and hide a breach of
// the 20 ms objective in the le="0.02" bucket; proxyOverheadMs truncates only the
// diagnostic JSON field. The provider leg arrives quantized to 1 ms (the context
// key that carries it stores whole milliseconds), so the sample can overstate
// overhead by just under 1 ms and never understates it — the safe direction for
// a ceiling objective.
func proxyOverheadDuration(ctx context.Context, now time.Time) (time.Duration, bool) {
	start, ok := RequestStartFromContext(ctx)
	if !ok {
		return 0, false
	}
	provider := time.Duration(0)
	if providerMs, ok := providerDurationMsFromContext(ctx); ok {
		provider = time.Duration(providerMs) * time.Millisecond
	}
	overhead := now.Sub(start) - provider
	if overhead < 0 {
		return 0, true
	}
	return overhead, true
}

// proxyOverheadMs is the whole-millisecond proxy_overhead_ms written to the
// embedded ibex block. Truncation is deliberate: the field is a diagnostic JSON
// integer, while the SLO reads the full-precision histogram sample produced by
// the same arithmetic.
func proxyOverheadMs(ctx context.Context) int64 {
	overhead, ok := proxyOverheadDuration(ctx, time.Now())
	if !ok {
		return 0
	}
	return overhead.Milliseconds()
}
