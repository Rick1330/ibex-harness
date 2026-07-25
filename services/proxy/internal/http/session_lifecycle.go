package http

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"strings"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/packages/session"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/asyncpool"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/llm"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/sessioncache"
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
type resolvedSession struct {
	SessionID  uuid.UUID
	ExternalID string
	TurnIndex  int
	OrgID      uuid.UUID
	AgentID    uuid.UUID
}

type sessionLifecycleDeps struct {
	store         session.Store
	cache         *sessioncache.Cache
	pool          *asyncpool.Pool
	getOrCreateTO time.Duration
	log           *logger.Logger
}

type getOrCreateInput struct {
	orgID        uuid.UUID
	agentID      uuid.UUID
	externalID   string
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
// Fail-open: returns nil and leaves the request unchanged on any error.
func (h chatCompletionHandler) resolveSessionForRequest(
	r *http.Request,
	parsed *llm.ChatCompletionRequest,
	providerName string,
) *http.Request {
	deps := h.lifecycle()
	if deps.store == nil {
		return r
	}
	resolved, err := deps.resolve(r.Context(), r.Header.Get(headerSessionID), parsed, providerName)
	if err != nil || resolved == nil {
		return r
	}
	return r.WithContext(withResolvedSession(r.Context(), *resolved))
}

func (d sessionLifecycleDeps) resolve(
	ctx context.Context,
	rawHeader string,
	parsed *llm.ChatCompletionRequest,
	providerName string,
) (*resolvedSession, error) {
	orgID, agentID, ok := tenantIDsFromContext(ctx)
	if !ok {
		return nil, nil
	}
	externalID, ok := stickyExternalID(rawHeader)
	if !ok {
		return nil, nil
	}
	lookup := sessioncache.LookupKey{OrgID: orgID, AgentID: agentID, ExternalID: externalID}
	if hit, ok := d.cacheLookup(ctx, lookup); ok {
		return hit, nil
	}
	return d.getOrCreateSession(ctx, getOrCreateInput{
		orgID: orgID, agentID: agentID, externalID: externalID,
		parsed: parsed, providerName: providerName,
	})
}

func stickyExternalID(rawHeader string) (string, bool) {
	externalID := strings.TrimSpace(rawHeader)
	if externalID == "" {
		return uuid.New().String(), true
	}
	if len(externalID) > maxExternalIDLen {
		return "", false
	}
	return externalID, true
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
	params := session.GetOrCreateParams{
		OrgID: in.orgID, AgentID: in.agentID, ExternalID: in.externalID,
		Model: in.parsed.Model, Provider: in.providerName,
		DirectiveVersionID: directiveVersionPtr(ctx),
	}
	sess, err := d.store.GetOrCreate(goCtx, params)
	if err != nil {
		d.warnGetOrCreate(ctx, err)
		return nil, err
	}
	d.cacheSet(ctx, sessioncache.LookupKey{
		OrgID: in.orgID, AgentID: in.agentID, ExternalID: in.externalID,
	}, sessioncache.Entry{SessionID: sess.ID, TurnCount: sess.TurnCount})
	return &resolvedSession{
		SessionID: sess.ID, ExternalID: in.externalID,
		TurnIndex: sess.TurnCount, OrgID: in.orgID, AgentID: in.agentID,
	}, nil
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
	if !ok {
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
	rs, ok := ResolvedSessionFromContext(ctx)
	if !ok {
		return
	}
	deps := h.lifecycle()
	if deps.store == nil || deps.pool == nil {
		return
	}
	params := buildCheckpointParams(rs, in, RequestIDFromContext(ctx))
	externalID := rs.ExternalID
	deps.pool.Submit(func() {
		deps.runCheckpoint(params, externalID)
	})
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
	// Detached from the HTTP request context so client disconnect cannot cancel
	// durable checkpoint writes (5s deadline per task).
	ctx, cancel := context.WithTimeout(context.Background(), checkpointTaskTimeout)
	defer cancel()
	err := d.store.AppendCheckpoint(ctx, params)
	if err == nil {
		d.cacheSet(ctx, sessioncache.LookupKey{
			OrgID: params.OrgID, AgentID: params.AgentID, ExternalID: externalID,
		}, sessioncache.Entry{SessionID: params.SessionID, TurnCount: params.TurnIndex + 1})
		return
	}
	if errors.Is(err, session.ErrDuplicateTurn) {
		if d.cache != nil {
			d.cache.Invalidate(ctx, sessioncache.LookupKey{
				OrgID: params.OrgID, AgentID: params.AgentID, ExternalID: externalID,
			})
		}
		return
	}
	if d.log != nil {
		d.log.WarnCtx(ctx, "session checkpoint failed",
			"error", err.Error(),
			"session_id", params.SessionID.String(),
			"turn_index", params.TurnIndex,
		)
	}
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

func readAllBody(r io.Reader) ([]byte, error) {
	return io.ReadAll(r)
}
