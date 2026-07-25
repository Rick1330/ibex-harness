package http

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"strings"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/packages/reqid"
	"github.com/Rick1330/ibex-harness/packages/session"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/asyncpool"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/llm"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/sessioncache"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/validation"
	"github.com/google/uuid"
)

const (
	headerSessionID       = "X-IBEX-Session-ID"
	checkpointTaskTimeout = 5 * time.Second
	defaultGetOrCreateTO  = 50 * time.Millisecond
	// maxExternalIDLen bounds sticky keys (UUID header max 36; pad for defense).
	maxExternalIDLen = 64
)

// resolvedSession holds hot-path session identity for response headers + checkpoint.
// SessionID == uuid.Nil means sticky-only (fail-open): emit response header, skip checkpoint.
type resolvedSession struct {
	SessionID  uuid.UUID
	ExternalID string
	TurnIndex  int
	OrgID      uuid.UUID
	AgentID    uuid.UUID
}

func (rs resolvedSession) durable() bool {
	return rs.SessionID != uuid.Nil
}

type sessionLifecycleDeps struct {
	store         session.Store
	cache         *sessioncache.Cache
	pool          *asyncpool.Pool
	getOrCreateTO time.Duration
	log           *logger.Logger
}

type getOrCreateInput struct {
	key          sessioncache.LookupKey
	parsed       *llm.ChatCompletionRequest
	providerName string
}

func (h chatCompletionHandler) lifecycle() sessionLifecycleDeps {
	to := h.getOrCreateTimeout
	if to <= 0 {
		to = defaultGetOrCreateTO
	}
	return sessionLifecycleDeps{
		store: h.sessionStore, cache: h.sessionCache, pool: h.checkpointPool,
		getOrCreateTO: to, log: h.log,
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
	externalID := stickyExternalID(r.Header.Get(headerSessionID))
	sticky := resolvedSession{ExternalID: externalID}
	ctx := withResolvedSession(r.Context(), sticky)
	r = r.WithContext(ctx)

	deps := h.lifecycle()
	if deps.store == nil {
		return r
	}
	resolved, err := deps.resolve(ctx, externalID, parsed, providerName)
	if err != nil || resolved == nil {
		return r
	}
	return r.WithContext(withResolvedSession(ctx, *resolved))
}

func (d sessionLifecycleDeps) resolve(
	ctx context.Context,
	externalID string,
	parsed *llm.ChatCompletionRequest,
	providerName string,
) (*resolvedSession, error) {
	orgID, agentID, ok := tenantIDsFromContext(ctx)
	if !ok {
		return nil, nil
	}
	lookup := sessioncache.LookupKey{OrgID: orgID, AgentID: agentID, ExternalID: externalID}
	if hit, ok := d.cacheLookup(ctx, lookup); ok {
		return hit, nil
	}
	return d.getOrCreateSession(ctx, getOrCreateInput{
		key: lookup, parsed: parsed, providerName: providerName,
	})
}

// stickyExternalID returns a bounded sticky key. Empty or oversized client
// values mint a fresh UUID so every request can still emit X-IBEX-Session-ID.
func stickyExternalID(rawHeader string) string {
	externalID := strings.TrimSpace(rawHeader)
	if externalID == "" || len(externalID) > maxExternalIDLen {
		return uuid.New().String()
	}
	return externalID
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
	orgID, err := uuid.Parse(authRes.OrgID)
	if err != nil {
		return uuid.Nil, uuid.Nil, false
	}
	return orgID, agent.ID, true
}

func (d sessionLifecycleDeps) cacheLookup(
	ctx context.Context,
	key sessioncache.LookupKey,
) (*resolvedSession, bool) {
	if d.cache == nil {
		return nil, false
	}
	e, ok := d.cache.Get(ctx, key)
	if !ok {
		return nil, false
	}
	// Reserve next turn optimistically. Gaps after failed turns are acceptable;
	// ErrDuplicateTurn + retryCheckpoint handles concurrent double-reads.
	d.cache.Set(ctx, key, sessioncache.Entry{
		SessionID: e.SessionID, TurnCount: e.TurnCount + 1,
	})
	return &resolvedSession{
		SessionID: e.SessionID, ExternalID: key.ExternalID,
		TurnIndex: e.TurnCount, OrgID: key.OrgID, AgentID: key.AgentID,
	}, true
}

func (d sessionLifecycleDeps) getOrCreateSession(
	ctx context.Context,
	in getOrCreateInput,
) (*resolvedSession, error) {
	goCtx, cancel := context.WithTimeout(ctx, d.getOrCreateTO)
	defer cancel()
	sess, err := d.store.GetOrCreate(goCtx, in.toParams(ctx))
	if err != nil {
		d.warnGetOrCreate(ctx, err)
		return nil, err
	}
	d.cacheSet(ctx, in.key, sessioncache.Entry{
		SessionID: sess.ID, TurnCount: sess.TurnCount + 1,
	})
	return in.toResolved(sess), nil
}

func (in getOrCreateInput) toParams(ctx context.Context) session.GetOrCreateParams {
	return session.GetOrCreateParams{
		OrgID: in.key.OrgID, AgentID: in.key.AgentID, ExternalID: in.key.ExternalID,
		Model: in.parsed.Model, Provider: in.providerName,
		DirectiveVersionID: directiveVersionPtr(ctx),
	}
}

func (in getOrCreateInput) toResolved(sess *session.Session) *resolvedSession {
	return &resolvedSession{
		SessionID: sess.ID, ExternalID: in.key.ExternalID,
		TurnIndex: sess.TurnCount, OrgID: in.key.OrgID, AgentID: in.key.AgentID,
	}
}

func directiveVersionPtr(ctx context.Context) *uuid.UUID {
	resolved, ok := ResolvedDirectiveFromContext(ctx)
	if !ok || resolved.VersionID == uuid.Nil {
		return nil
	}
	id := resolved.VersionID
	return &id
}

func (d sessionLifecycleDeps) cacheSet(
	ctx context.Context,
	key sessioncache.LookupKey,
	entry sessioncache.Entry,
) {
	if d.cache == nil {
		return
	}
	d.cache.Set(ctx, key, entry)
}

func (d sessionLifecycleDeps) warnGetOrCreate(ctx context.Context, err error) {
	if d.log == nil {
		return
	}
	d.log.WarnCtx(ctx, "session get_or_create failed; continuing without session",
		"error", err.Error())
}

func setSessionResponseHeader(w http.ResponseWriter, ctx context.Context) {
	rs, ok := ResolvedSessionFromContext(ctx)
	if !ok || rs.ExternalID == "" {
		return
	}
	w.Header().Set(headerSessionID, rs.ExternalID)
}

type checkpointInput struct {
	Messages       []llm.Message
	CompletionText string
	Model          string
	Provider       string
	Usage          *provider.Usage
	Latency        time.Duration
	ProviderReqID  string
	IsStreaming    bool
	IsComplete     bool
}

func (h chatCompletionHandler) enqueueCheckpoint(ctx context.Context, in checkpointInput) {
	h.enqueuePostResponse(ctx, in, requestOutcome{
		StatusCode: 200,
		IsComplete: in.IsComplete,
	})
}

// enqueuePostResponse runs optional checkpoint + trace emit on the bounded pool.
// Never blocks the LLM response path longer than Submit queue wait; Write is non-blocking.
func (h chatCompletionHandler) enqueuePostResponse(
	ctx context.Context,
	in checkpointInput,
	outcome requestOutcome,
) {
	snap, snapOK := h.captureTraceSnapshot(ctx, in, outcome)
	deps := h.lifecycle()
	doCheckpoint := wantSessionCheckpoint(ctx, deps, in, outcome)
	doTrace := h.traceWriter != nil && snapOK
	if !doCheckpoint && !doTrace {
		return
	}
	h.submitPostResponse(ctx, deps, in, snap, doCheckpoint, doTrace)
}

// wantSessionCheckpoint is true for successful or streaming turns with a durable session.
// Provider-failure traces (non-stream, incomplete) must not append empty checkpoints.
func wantSessionCheckpoint(
	ctx context.Context,
	deps sessionLifecycleDeps,
	in checkpointInput,
	outcome requestOutcome,
) bool {
	if deps.store == nil {
		return false
	}
	rs, ok := ResolvedSessionFromContext(ctx)
	if !ok || !rs.durable() {
		return false
	}
	return outcome.IsComplete || in.IsStreaming
}

func (h chatCompletionHandler) submitPostResponse(
	ctx context.Context,
	deps sessionLifecycleDeps,
	in checkpointInput,
	snap traceAssembleInput,
	doCheckpoint, doTrace bool,
) {
	var params session.CheckpointParams
	var externalID string
	if doCheckpoint {
		rs, _ := ResolvedSessionFromContext(ctx)
		params = buildCheckpointParams(rs, in, RequestIDFromContext(ctx))
		externalID = rs.ExternalID
	}
	run := func() {
		if doCheckpoint {
			deps.runCheckpoint(params, externalID)
		}
		if doTrace {
			h.emitTrace(snap)
		}
	}
	if deps.pool != nil {
		deps.pool.Submit(run)
		return
	}
	run()
}

func (h chatCompletionHandler) captureTraceSnapshot(
	ctx context.Context,
	in checkpointInput,
	outcome requestOutcome,
) (traceAssembleInput, bool) {
	orgID, agentID, ok := tenantIDsFromContext(ctx)
	if !ok {
		return traceAssembleInput{}, false
	}
	reqID := RequestIDFromContext(ctx)
	if reqID == "" {
		return traceAssembleInput{}, false
	}
	completed := time.Now().UTC()
	requested := completed
	if start, ok := RequestStartFromContext(ctx); ok {
		requested = start.UTC()
	}
	var sessionID *uuid.UUID
	if id, ok := durableSessionID(ctx); ok {
		sessionID = &id
	}
	status := outcome.StatusCode
	if status == 0 {
		if outcome.IsComplete {
			status = 200
		}
	}
	return traceAssembleInput{
		RequestID: reqID,
		OrgID:     orgID,
		AgentID:   agentID,
		SessionID: sessionID,
		Model:     in.Model,
		Provider:  in.Provider,
		Streaming: in.IsStreaming,
		Usage:     in.Usage,
		Timings: requestTimings{
			AuthMs:       AuthLatencyMsFromContext(ctx),
			DirectiveMs:  DirectiveLatencyMsFromContext(ctx),
			ProviderTTFB: in.Latency,
			RequestedAt:  requested,
			CompletedAt:  completed,
		},
		Outcome: requestOutcome{
			StatusCode: status,
			IsComplete: outcome.IsComplete,
			ErrorCode:  outcome.ErrorCode,
		},
	}, true
}

func durableSessionID(ctx context.Context) (uuid.UUID, bool) {
	rs, ok := ResolvedSessionFromContext(ctx)
	if !ok {
		return uuid.Nil, false
	}
	if !rs.durable() {
		return uuid.Nil, false
	}
	return rs.SessionID, true
}

func (h chatCompletionHandler) emitTrace(snap traceAssembleInput) {
	rec := assembleTrace(snap)
	err := h.traceWriter.Write(rec)
	if err == nil {
		return
	}
	if h.log == nil {
		return
	}
	h.log.WarnCtx(context.Background(), "trace emit failed",
		"error", err,
		"request_id", snap.RequestID,
		"org_id", snap.OrgID.String(),
	)
}

func buildCheckpointParams(rs resolvedSession, in checkpointInput, requestID string) session.CheckpointParams {
	inputTok, outputTok := usageTokens(in.Usage)
	return session.CheckpointParams{
		SessionID: rs.SessionID, OrgID: rs.OrgID, AgentID: rs.AgentID,
		TurnIndex: rs.TurnIndex, RequestID: requestID,
		MessagesHash: hashLLMMessages(in.Messages),
		InputTokens:  inputTok, OutputTokens: outputTok,
		Model: in.Model, Provider: in.Provider,
		CompletionHash:    session.HashText(in.CompletionText),
		LatencyMs:         int(in.Latency / time.Millisecond),
		ProviderRequestID: in.ProviderReqID,
		IsStreaming:       in.IsStreaming, IsComplete: in.IsComplete,
	}
}

func usageTokens(u *provider.Usage) (int, int) {
	if u == nil {
		return 0, 0
	}
	return u.InputTokens, u.OutputTokens
}

func hashLLMMessages(msgs []llm.Message) string {
	out := make([]session.MessageForHash, len(msgs))
	for i, m := range msgs {
		out[i] = session.MessageForHash{Role: m.Role, Content: m.Content}
	}
	return session.HashMessages(out)
}

func (d sessionLifecycleDeps) runCheckpoint(params session.CheckpointParams, externalID string) {
	ctx, cancel := context.WithTimeout(context.Background(), checkpointTaskTimeout)
	defer cancel()
	if params.RequestID != "" {
		ctx = reqid.WithRequestID(ctx, params.RequestID)
	}
	err := d.store.AppendCheckpoint(ctx, params)
	if err == nil {
		d.cacheSet(ctx, sessioncache.LookupKey{
			OrgID: params.OrgID, AgentID: params.AgentID, ExternalID: externalID,
		}, sessioncache.Entry{SessionID: params.SessionID, TurnCount: params.TurnIndex + 1})
		return
	}
	if errors.Is(err, session.ErrDuplicateTurn) {
		d.retryCheckpoint(ctx, params, externalID)
		return
	}
	d.warnCheckpoint(ctx, params, err)
}

func (d sessionLifecycleDeps) retryCheckpoint(
	ctx context.Context,
	params session.CheckpointParams,
	externalID string,
) {
	if d.cache != nil {
		d.cache.Invalidate(ctx, sessioncache.LookupKey{
			OrgID: params.OrgID, AgentID: params.AgentID, ExternalID: externalID,
		})
	}
	sess, err := d.store.GetOrCreate(ctx, session.GetOrCreateParams{
		OrgID: params.OrgID, AgentID: params.AgentID, ExternalID: externalID,
		Model: params.Model, Provider: params.Provider,
	})
	if err != nil {
		d.warnCheckpoint(ctx, params, err)
		return
	}
	params.SessionID = sess.ID
	params.TurnIndex = sess.TurnCount
	if err := d.store.AppendCheckpoint(ctx, params); err != nil {
		d.warnCheckpoint(ctx, params, err)
		return
	}
	d.cacheSet(ctx, sessioncache.LookupKey{
		OrgID: params.OrgID, AgentID: params.AgentID, ExternalID: externalID,
	}, sessioncache.Entry{SessionID: sess.ID, TurnCount: params.TurnIndex + 1})
}

func (d sessionLifecycleDeps) warnCheckpoint(ctx context.Context, params session.CheckpointParams, err error) {
	if d.log == nil {
		return
	}
	d.log.WarnCtx(ctx, "session checkpoint failed",
		"error", err.Error(),
		"session_id", params.SessionID.String(),
		"turn_index", params.TurnIndex,
	)
}

func completionTextFromJSON(body []byte) string {
	var wire struct {
		Choices []struct {
			Message struct {
				Content string `json:"content"`
			} `json:"message"`
		} `json:"choices"`
	}
	if err := json.Unmarshal(body, &wire); err != nil || len(wire.Choices) == 0 {
		return ""
	}
	return wire.Choices[0].Message.Content
}

func readLimitedBody(r io.Reader, limit int64) ([]byte, error) {
	limited := io.LimitReader(r, limit+1)
	body, err := io.ReadAll(limited)
	if err != nil {
		return nil, err
	}
	if int64(len(body)) > limit {
		return nil, errProviderResponseTooLarge
	}
	return body, nil
}

var errProviderResponseTooLarge = errors.New("provider response exceeds size limit")

func readAllBody(r io.Reader) ([]byte, error) {
	return readLimitedBody(r, validation.MaxProviderResponseBytes)
}

func writeJSONBody(w http.ResponseWriter, body []byte) {
	// Opaque OpenAI-compatible JSON passthrough (Content-Type: application/json).
	// Not an HTML response; Codacy/Opengrep XSS on ResponseWriter is a false positive.
	_, _ = io.Copy(w, bytes.NewReader(body)) // nosemgrep: go.lang.security.audit.xss.no-direct-write-to-responsewriter.no-direct-write-to-responsewriter
}
