package http

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"strings"
	"time"

	apierror "github.com/Rick1330/ibex-harness/packages/apierror"
	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/packages/reqid"
	"github.com/Rick1330/ibex-harness/packages/session"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/extractionbuffer"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/extractionenqueue"
	"github.com/google/uuid"
)

type terminateRequestBody struct {
	Reason string `json:"reason"`
	Status string `json:"status"`
}

type terminateResponseData struct {
	SessionID    string `json:"session_id"`
	FinalStatus  string `json:"final_status"`
	TerminatedAt string `json:"terminated_at"`
}

type sessionTerminateHandler struct {
	store    session.Store
	buffer   *extractionbuffer.Buffer
	enqueue  *extractionenqueue.Client
	log      *logger.Logger
	metrics  *metrics.ProxyRegistry
	docsBase string
}

type terminateIdentity struct {
	orgID      uuid.UUID
	agentID    uuid.UUID
	externalID string
	requestID  string
}

func (h sessionTerminateHandler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	if !requireMethod(w, r, http.MethodPost, h.docsBase) {
		return
	}
	id, ok := h.resolveTerminateIdentity(w, r)
	if !ok {
		return
	}
	if !h.validateTerminateBody(w, r, id.requestID) {
		return
	}
	result, sessionID, ok := h.completeSession(w, r, id)
	if !ok {
		return
	}
	writeTerminateOK(w, id.externalID)
	if result == session.CompleteOK {
		go h.afterCompleteOK(id.orgID, id.agentID, sessionID, id.externalID, id.requestID)
	}
}

func (h sessionTerminateHandler) resolveTerminateIdentity(
	w http.ResponseWriter, r *http.Request,
) (terminateIdentity, bool) {
	requestID := requestIDFromContext(r.Context())
	externalID := strings.TrimSpace(r.PathValue("session_id"))
	if externalID == "" {
		apierror.WriteStatus(w, http.StatusBadRequest, apierror.CodeValidationError,
			"Request validation failed", requestID,
			apierror.WriteOpts{Detail: "session_id path parameter is required", DocsBase: h.docsBase})
		return terminateIdentity{}, false
	}
	authRes, ok := auth.FromContext(r.Context())
	if !ok {
		apierror.WriteStatus(w, http.StatusInternalServerError, apierror.CodeInternalError,
			msgInternalError, requestID,
			apierror.WriteOpts{Detail: "missing auth context", DocsBase: h.docsBase})
		return terminateIdentity{}, false
	}
	agent, ok := AgentFromContext(r.Context())
	if !ok {
		apierror.WriteStatus(w, http.StatusInternalServerError, apierror.CodeInternalError,
			msgInternalError, requestID,
			apierror.WriteOpts{Detail: "missing agent context", DocsBase: h.docsBase})
		return terminateIdentity{}, false
	}
	return terminateIdentity{
		orgID: authRes.OrgID, agentID: agent.ID, externalID: externalID, requestID: requestID,
	}, true
}

func (h sessionTerminateHandler) validateTerminateBody(
	w http.ResponseWriter, r *http.Request, requestID string,
) bool {
	body, ok := parseTerminateBody(w, r, requestID, h.docsBase)
	if !ok {
		return false
	}
	if body.Status != session.StatusCompleted {
		apierror.WriteStatus(w, http.StatusBadRequest, apierror.CodeValidationError,
			"Request validation failed", requestID,
			apierror.WriteOpts{Detail: `status must be "completed"`, DocsBase: h.docsBase})
		return false
	}
	return true
}

func (h sessionTerminateHandler) completeSession(
	w http.ResponseWriter, r *http.Request, id terminateIdentity,
) (session.CompleteResult, uuid.UUID, bool) {
	if h.store == nil {
		apierror.WriteStatus(w, http.StatusServiceUnavailable, apierror.CodeServiceDegraded,
			"Session store unavailable", id.requestID, apierror.WriteOpts{DocsBase: h.docsBase})
		return 0, uuid.Nil, false
	}
	result, sessionID, err := h.store.CompleteByExternalID(r.Context(), id.orgID, id.agentID, id.externalID)
	if err != nil {
		if h.log != nil {
			h.log.ErrorCtx(r.Context(), "session complete failed", "error", err)
		}
		apierror.WriteStatus(w, http.StatusServiceUnavailable, apierror.CodeServiceDegraded,
			"Session terminate failed", id.requestID, apierror.WriteOpts{DocsBase: h.docsBase})
		return 0, uuid.Nil, false
	}
	if result == session.CompleteNotFound {
		apierror.WriteStatus(w, http.StatusNotFound, apierror.CodeInvalidRequest,
			"Session not found", id.requestID, apierror.WriteOpts{DocsBase: h.docsBase})
		return 0, uuid.Nil, false
	}
	return result, sessionID, true
}

func parseTerminateBody(w http.ResponseWriter, r *http.Request, requestID, docsBase string) (terminateRequestBody, bool) {
	defer func() { _ = r.Body.Close() }()
	raw, err := io.ReadAll(io.LimitReader(r.Body, 1<<20))
	if err != nil {
		apierror.WriteStatus(w, http.StatusBadRequest, apierror.CodeInvalidJSON,
			"Malformed JSON in request body", requestID, apierror.WriteOpts{DocsBase: docsBase})
		return terminateRequestBody{}, false
	}
	var body terminateRequestBody
	if err := json.Unmarshal(raw, &body); err != nil {
		apierror.WriteStatus(w, http.StatusBadRequest, apierror.CodeInvalidJSON,
			"Malformed JSON in request body", requestID, apierror.WriteOpts{DocsBase: docsBase})
		return terminateRequestBody{}, false
	}
	body.Status = strings.TrimSpace(body.Status)
	return body, true
}

func writeTerminateOK(w http.ResponseWriter, externalID string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	_ = json.NewEncoder(w).Encode(map[string]any{
		"data": terminateResponseData{
			SessionID:    externalID,
			FinalStatus:  session.StatusCompleted,
			TerminatedAt: time.Now().UTC().Format(time.RFC3339Nano),
		},
	})
}

func (h sessionTerminateHandler) afterCompleteOK(
	orgID, agentID, sessionID uuid.UUID, externalID, requestID string,
) {
	ctx, cancel := context.WithTimeout(context.Background(), extractionenqueue.DefaultTimeout+time.Second)
	defer cancel()
	if requestID != "" {
		ctx = reqid.WithRequestID(ctx, requestID)
	}

	turns, err := h.takeTurns(ctx, orgID, agentID, externalID)
	if err != nil {
		h.recordEnqueue("failed", "buffer_read")
		if h.log != nil {
			h.log.WarnCtx(ctx, "extraction buffer take failed", "error", err, "external_id", externalID)
		}
		return
	}
	if len(turns) == 0 {
		h.recordEnqueue("skipped", "empty_buffer")
		return
	}
	if h.enqueue == nil || !h.enqueue.Enabled() {
		h.recordEnqueue("skipped", "disabled")
		return
	}
	req := extractionenqueue.Request{
		OrgID: orgID, AgentID: agentID, SessionID: sessionID,
		Turns: toEnqueueTurns(turns),
	}
	if err := h.enqueue.Enqueue(ctx, req); err != nil {
		h.recordEnqueue("failed", "http")
		if h.log != nil {
			h.log.WarnCtx(ctx, "extraction enqueue failed", "error", err, "session_id", sessionID.String())
		}
		return
	}
	h.recordEnqueue("success", "ok")
}

func (h sessionTerminateHandler) takeTurns(
	ctx context.Context, orgID, agentID uuid.UUID, externalID string,
) ([]extractionbuffer.Turn, error) {
	if h.buffer == nil {
		return nil, nil
	}
	return h.buffer.Take(ctx, extractionbuffer.LookupKey{
		OrgID: orgID, AgentID: agentID, ExternalID: externalID,
	})
}

func (h sessionTerminateHandler) recordEnqueue(result, reason string) {
	if h.metrics != nil {
		h.metrics.IncExtractionEnqueue(result, reason)
	}
}

func toEnqueueTurns(in []extractionbuffer.Turn) []extractionenqueue.Turn {
	out := make([]extractionenqueue.Turn, len(in))
	for i, t := range in {
		out[i] = extractionenqueue.Turn{TurnIndex: t.TurnIndex, Role: t.Role, Content: t.Content}
	}
	return out
}
