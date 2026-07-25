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
	serviceCtx    context.Context
	getOrCreateTO time.Duration
	log           *logger.Logger
}

func (h chatCompletionHandler) lifecycle() sessionLifecycleDeps {
	to := h.getOrCreateTimeout
	if to <= 0 {
		to = defaultGetOrCreateTO
	}
	svc := h.serviceCtx
	if svc == nil {
		svc = context.Background()
	}
	return sessionLifecycleDeps{
		store: h.sessionStore, cache: h.sessionCache, pool: h.checkpointPool,
		serviceCtx: svc, getOrCreateTO: to, log: h.log,
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
	externalID := strings.TrimSpace(rawHeader)
	if externalID == "" {
		externalID = uuid.New().String()
	}
	if hit, ok := d.cacheLookup(ctx, orgID, agentID, externalID); ok {
		return hit, nil
	}
	return d.getOrCreateSession(ctx, orgID, agentID, externalID, parsed, providerName)
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
	orgID, agentID uuid.UUID,
	externalID string,
) (*resolvedSession, bool) {
	if d.cache == nil {
		return nil, false
	}
	e, ok := d.cache.Get(ctx, orgID, agentID, externalID)
	if !ok {
		return nil, false
	}
	return &resolvedSession{
		SessionID: e.SessionID, ExternalID: externalID,
		TurnIndex: e.TurnCount, OrgID: orgID, AgentID: agentID,
	}, true
}

func (d sessionLifecycleDeps) getOrCreateSession(
	ctx context.Context,
	orgID, agentID uuid.UUID,
	externalID string,
	parsed *llm.ChatCompletionRequest,
	providerName string,
) (*resolvedSession, error) {
	goCtx, cancel := context.WithTimeout(ctx, d.getOrCreateTO)
	defer cancel()
	params := session.GetOrCreateParams{
		OrgID: orgID, AgentID: agentID, ExternalID: externalID,
		Model: parsed.Model, Provider: providerName,
		DirectiveVersionID: directiveVersionPtr(ctx),
	}
	sess, err := d.store.GetOrCreate(goCtx, params)
	if err != nil {
		d.warnGetOrCreate(ctx, err)
		return nil, err
	}
	d.cacheSet(ctx, orgID, agentID, externalID, sess.ID, sess.TurnCount)
	return &resolvedSession{
		SessionID: sess.ID, ExternalID: externalID,
		TurnIndex: sess.TurnCount, OrgID: orgID, AgentID: agentID,
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
	orgID, agentID uuid.UUID,
	externalID string,
	sessionID uuid.UUID,
	turnCount int,
) {
	if d.cache == nil {
		return
	}
	d.cache.Set(ctx, orgID, agentID, externalID, sessioncache.Entry{
		SessionID: sessionID, TurnCount: turnCount,
	})
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
	deps.pool.Submit(func() {
		deps.runCheckpoint(params, rs.ExternalID)
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
	ctx, cancel := context.WithTimeout(d.serviceCtx, checkpointTaskTimeout)
	defer cancel()
	err := d.store.AppendCheckpoint(ctx, params)
	if err == nil {
		d.cacheSet(ctx, params.OrgID, params.AgentID, externalID, params.SessionID, params.TurnIndex+1)
		return
	}
	if errors.Is(err, session.ErrDuplicateTurn) {
		if d.cache != nil {
			d.cache.Invalidate(ctx, params.OrgID, params.AgentID, externalID)
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
