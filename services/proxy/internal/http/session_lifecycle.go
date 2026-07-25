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
// On store miss/error it still attaches a sticky external_id so the response
// can echo X-IBEX-Session-ID; checkpoints are skipped until SessionID is set.
func (h chatCompletionHandler) resolveSessionForRequest(
	r *http.Request,
	parsed *llm.ChatCompletionRequest,
	providerName string,
) *http.Request {
	externalID, ok := stickyExternalID(r.Header.Get(headerSessionID))
	if !ok {
		return r
	}
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
	// Reserve the next index in cache so concurrent hits prefer distinct turns.
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
	}, sessioncache.Entry{SessionID: sess.ID, TurnCount: sess.TurnCount + 1})
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
	rs, ok := ResolvedSessionFromContext(ctx)
	if !ok || !rs.durable() {
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
	return readLimitedBody(r, validation.MaxRequestBodyBytes)
}

func writeJSONBody(w http.ResponseWriter, body []byte) {
	// Opaque OpenAI-compatible JSON passthrough (Content-Type: application/json).
	// Not an HTML response; Codacy/Opengrep XSS on ResponseWriter is a false positive.
	_, _ = io.Copy(w, bytes.NewReader(body)) // nosemgrep: go.lang.security.audit.xss.no-direct-write-to-responsewriter.no-direct-write-to-responsewriter
}
