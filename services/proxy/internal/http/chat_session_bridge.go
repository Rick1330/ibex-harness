package http

import (
	"context"
	"net/http"
	"time"

	"github.com/Rick1330/ibex-harness/packages/billing"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	httpsession "github.com/Rick1330/ibex-harness/services/proxy/internal/http/session"
	httptrace "github.com/Rick1330/ibex-harness/services/proxy/internal/http/trace"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/llm"
	"github.com/google/uuid"
)

// Type aliases keep call sites readable while types live in subpackages.
type (
	checkpointInput = httpsession.CheckpointInput
	requestOutcome  = httptrace.RequestOutcome
	TraceWriter     = httptrace.TraceWriter
)

func (h chatCompletionHandler) lifecycle() httpsession.LifecycleDeps {
	return httpsession.LifecycleDeps{
		Store: h.sessionStore, Cache: h.sessionCache, Pool: h.checkpointPool,
		GetOrCreateTO: h.getOrCreateTimeout, Log: h.log, TurnBuffer: h.turnBuffer,
		Evidence: httpsession.EffectiveEvidence(h.evidenceStore),
	}
}

// resolveSessionForRequest mints/looks up a session before LLM forward.
// On store miss/error it still attaches a sticky external_id so the response
// can echo X-IBEX-Session-ID; checkpoints are skipped until SessionID is set.
func (h chatCompletionHandler) resolveSessionForRequest(
	r *http.Request,
	parsed *llm.ChatCompletionRequest,
	providerName string,
) *http.Request {
	externalID := httpsession.StickyExternalID(r.Header.Get(httpsession.HeaderSessionID))
	sticky := httpsession.Resolved{ExternalID: externalID}
	ctx := withResolvedSession(r.Context(), sticky)
	r = r.WithContext(ctx)

	deps := h.lifecycle()
	if deps.Store == nil {
		return r
	}
	orgID, agentID, ok := tenantIDsFromContext(ctx)
	if !ok {
		return r
	}
	resolved, err := deps.Resolve(ctx, httpsession.ResolveInput{
		ExternalID: externalID, OrgID: orgID, AgentID: agentID,
		DirectiveVersionID: directiveVersionPtr(ctx),
		Parsed:             parsed, ProviderName: providerName,
	})
	if err != nil || resolved == nil {
		return r
	}
	return r.WithContext(withResolvedSession(ctx, *resolved))
}

func tenantIDsFromContext(ctx context.Context) (uuid.UUID, uuid.UUID, bool) {
	agent, ok := AgentFromContext(ctx)
	if !ok {
		return uuid.Nil, uuid.Nil, false
	}
	authRes, ok := auth.FromContext(ctx)
	if !ok {
		return uuid.Nil, uuid.Nil, false
	}
	if authRes.OrgID == uuid.Nil {
		return uuid.Nil, uuid.Nil, false
	}
	return authRes.OrgID, agent.ID, true
}

func directiveVersionPtr(ctx context.Context) *uuid.UUID {
	resolved, ok := ResolvedDirectiveFromContext(ctx)
	if !ok || resolved.VersionID == uuid.Nil {
		return nil
	}
	id := resolved.VersionID
	return &id
}

func setSessionResponseHeader(w http.ResponseWriter, ctx context.Context) {
	rs, ok := ResolvedSessionFromContext(ctx)
	if !ok {
		return
	}
	httpsession.SetResponseHeader(w, rs)
}

func (h chatCompletionHandler) enqueueCheckpoint(ctx context.Context, in checkpointInput) {
	h.enqueuePostResponse(ctx, in, requestOutcome{
		StatusCode: 200,
		IsComplete: in.IsComplete,
	})
}

// enqueuePostResponse runs optional checkpoint + trace emit on the bounded pool.
func (h chatCompletionHandler) enqueuePostResponse(
	ctx context.Context,
	in checkpointInput,
	outcome requestOutcome,
) {
	rs, _ := ResolvedSessionFromContext(ctx)
	meta := snapshotMetaFromContext(ctx)
	job := httpsession.PreparePostResponse(httpsession.PreparePostResponseInput{
		Deps:            h.lifecycle(),
		Writer:          httptrace.EffectiveWriter(h.traceWriter),
		UsageFactWriter: h.usageFactWriter,
		UsageFact:       h.freezeUsageFact(ctx, meta, in),
		Log:             h.log,
		Resolved:        rs,
		Meta:            meta,
		In:              in,
		Outcome:         outcome,
	})
	httpsession.EnqueuePostResponse(job)
}

// freezeUsageFact builds a write-time frozen usage_facts row (estimate + rate card version).
// Returns nil when the writer is disabled or tenant ids are missing.
func (h chatCompletionHandler) freezeUsageFact(
	ctx context.Context,
	meta httpsession.SnapshotMeta,
	in checkpointInput,
) *billing.UsageFact {
	if !canFreezeUsageFact(h.usageFactWriter, meta) {
		return nil
	}
	return buildFrozenUsageFact(ctx, freezeUsageFactInput{
		meta:        meta,
		in:          in,
		budgetCache: h.budgetCache,
	})
}

func canFreezeUsageFact(writer *billing.UsageFactWriter, meta httpsession.SnapshotMeta) bool {
	if writer == nil {
		return false
	}
	return metaHasTenantIDs(meta)
}

func metaHasTenantIDs(meta httpsession.SnapshotMeta) bool {
	if meta.OrgID == uuid.Nil {
		return false
	}
	return meta.AgentID != uuid.Nil
}

type freezeUsageFactInput struct {
	meta        httpsession.SnapshotMeta
	in          checkpointInput
	budgetCache *billing.Cache
}

func buildFrozenUsageFact(ctx context.Context, p freezeUsageFactInput) *billing.UsageFact {
	card := resolvePublishedCard(ctx, p.budgetCache, p.meta.OrgID)
	inTok, outTok := tokenCounts(p.in)
	cents, ver, ok := estimateCostChecked(estimateCostInput{
		card: card, provider: p.in.Provider, model: p.in.Model, inTok: inTok, outTok: outTok,
	})
	if !ok {
		// Do not persist EstimatedCostCents=0 for failed estimates (would corrupt spend).
		return nil
	}
	occurred := p.meta.RequestedAt
	if occurred.IsZero() {
		occurred = time.Now().UTC()
	}
	return &billing.UsageFact{
		RequestID:          p.meta.RequestID,
		OrgID:              p.meta.OrgID,
		AgentID:            p.meta.AgentID,
		Provider:           p.in.Provider,
		Model:              p.in.Model,
		OriginalModel:      optionalStringPtr(p.in.OriginalModel),
		FallbackModel:      optionalStringPtr(p.in.FallbackModel),
		FallbackReason:     p.in.FallbackReason,
		InputTokens:        clampUint32Tokens(inTok),
		OutputTokens:       clampUint32Tokens(outTok),
		TotalTokens:        clampUint32Tokens(safeAddInt64(inTok, outTok)),
		EstimatedCostCents: cents,
		RateCardVersion:    ver,
		Completeness:       usageCompleteness(p.in),
		OccurredAt:         occurred,
	}
}

func usageCompleteness(in checkpointInput) string {
	if in.Usage != nil && in.IsComplete {
		return "complete"
	}
	return "partial"
}

func resolvePublishedCard(ctx context.Context, cache *billing.Cache, orgID uuid.UUID) billing.CardVersion {
	card := billing.CardVersion{Version: "0"}
	if cache == nil {
		return card
	}
	published, err := cache.PublishedCard(ctx, orgID)
	if err != nil {
		return card
	}
	if published.Version == "" {
		return card
	}
	return published
}

func tokenCounts(in checkpointInput) (inTok, outTok int64) {
	if in.Usage == nil {
		return 0, 0
	}
	return int64(in.Usage.InputTokens), int64(in.Usage.OutputTokens)
}

type estimateCostInput struct {
	card     billing.CardVersion
	provider string
	model    string
	inTok    int64
	outTok   int64
}

func estimateCostChecked(in estimateCostInput) (int64, string, bool) {
	cents, ver, err := billing.EstimateCost(in.card, billing.TokenUsage{
		Provider: in.provider, Model: in.model, InputTokens: in.inTok, OutputTokens: in.outTok,
	})
	if err != nil {
		return 0, "", false
	}
	return cents, ver, true
}

func optionalStringPtr(s string) *string {
	if s == "" {
		return nil
	}
	out := s
	return &out
}

func clampUint32Tokens(n int64) uint32 {
	if n <= 0 {
		return 0
	}
	if n > int64(^uint32(0)) {
		return ^uint32(0)
	}
	return uint32(n)
}

func safeAddInt64(a, b int64) int64 {
	a = maxInt64(a, 0)
	b = maxInt64(b, 0)
	if a > (1<<63-1)-b {
		return 1<<63 - 1
	}
	return a + b
}

func maxInt64(a, b int64) int64 {
	if a > b {
		return a
	}
	return b
}

func snapshotMetaFromContext(ctx context.Context) httpsession.SnapshotMeta {
	orgID, agentID, _ := tenantIDsFromContext(ctx)
	meta := httpsession.SnapshotMeta{
		RequestID:          RequestIDFromContext(ctx),
		TraceID:            traceIDFromContext(ctx),
		RootSpanID:         spanIDFromContext(ctx),
		OrgID:              orgID,
		AgentID:            agentID,
		DirectiveVersionID: directiveVersionPtr(ctx),
		AuthMs:             AuthLatencyMsFromContext(ctx),
		DirectiveMs:        DirectiveLatencyMsFromContext(ctx),
	}
	if id, ok := durableSessionID(ctx); ok {
		meta.SessionID = &id
	}
	if assemble, ok := contextAssembleMetaFromContext(ctx); ok {
		if assemble.AssemblyMs > 0 {
			meta.ContextAssemblyMs = uint32(assemble.AssemblyMs)
		}
		meta.ScoreSchema = assemble.ScoreSchema
		meta.EvidenceExtras = assemble.EvidenceExtras
	}
	if start, ok := RequestStartFromContext(ctx); ok {
		meta.RequestedAt = start
	}
	return meta
}

func durableSessionID(ctx context.Context) (uuid.UUID, bool) {
	rs, ok := ResolvedSessionFromContext(ctx)
	if !ok || !rs.Durable() {
		return uuid.Nil, false
	}
	return rs.SessionID, true
}
