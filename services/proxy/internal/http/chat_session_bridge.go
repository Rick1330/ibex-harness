package http

import (
	"context"
	"net/http"

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
		GetOrCreateTO: h.getOrCreateTimeout, Log: h.log,
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
	job := httpsession.PreparePostResponse(httpsession.PreparePostResponseInput{
		Deps:     h.lifecycle(),
		Writer:   httptrace.EffectiveWriter(h.traceWriter),
		Log:      h.log,
		Resolved: rs,
		Meta:     snapshotMetaFromContext(ctx),
		In:       in,
		Outcome:  outcome,
	})
	httpsession.EnqueuePostResponse(job)
}

func snapshotMetaFromContext(ctx context.Context) httpsession.SnapshotMeta {
	orgID, agentID, _ := tenantIDsFromContext(ctx)
	meta := httpsession.SnapshotMeta{
		RequestID:   RequestIDFromContext(ctx),
		OrgID:       orgID,
		AgentID:     agentID,
		AuthMs:      AuthLatencyMsFromContext(ctx),
		DirectiveMs: DirectiveLatencyMsFromContext(ctx),
	}
	if id, ok := durableSessionID(ctx); ok {
		meta.SessionID = &id
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
