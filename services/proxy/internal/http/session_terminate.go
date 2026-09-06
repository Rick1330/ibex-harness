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
		bg := context.WithoutCancel(r.Context())
		go h.afterCompleteOK(bg, terminateEnqueueJob{
			orgID: id.orgID, agentID: id.agentID, sessionID: sessionID,
			externalID: id.externalID, requestID: id.requestID,
		})
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

type terminateEnqueueJob struct {
	orgID      uuid.UUID
	agentID    uuid.UUID
	sessionID  uuid.UUID
	externalID string
	requestID  string
}

func (h sessionTerminateHandler) afterCompleteOK(parent context.Context, job terminateEnqueueJob) {
	ctx, cancel := context.WithTimeout(parent, extractionenqueue.DefaultTimeout+time.Second)
	defer cancel()
	if job.requestID != "" {
		ctx = reqid.WithRequestID(ctx, job.requestID)
	}
	turns, ok := h.loadEnqueueTurns(ctx, job)
	if !ok {
		return
	}
	h.dispatchEnqueue(ctx, job, turns)
}

func (h sessionTerminateHandler) loadEnqueueTurns(
	ctx context.Context, job terminateEnqueueJob,
) ([]extractionbuffer.Turn, bool) {
	turns, err := h.peekTurns(ctx, job)
	if err != nil {
		h.recordEnqueue("failed", "buffer_read")
		if h.log != nil {
			h.log.WarnCtx(ctx, "extraction buffer peek failed", "error", err, "external_id", job.externalID)
		}
		return nil, false
	}
	if len(turns) == 0 {
		h.recordEnqueue("skipped", "empty_buffer")
		return nil, false
	}
	return turns, true
}

func (h sessionTerminateHandler) dispatchEnqueue(
	ctx context.Context, job terminateEnqueueJob, turns []extractionbuffer.Turn,
) {
	if !h.enqueueReady() {
		h.recordEnqueue("skipped", "disabled")
		return
	}
	if err := h.postEnqueue(ctx, job, turns); err != nil {
		h.failEnqueue(ctx, job, err)
		return
	}
	h.ackAfterSuccess(ctx, job)
}

func (h sessionTerminateHandler) enqueueReady() bool {
	if h.enqueue == nil {
		return false
	}
	return h.enqueue.Enabled()
}

func (h sessionTerminateHandler) failEnqueue(ctx context.Context, job terminateEnqueueJob, err error) {
	h.recordEnqueue("failed", "http")
	if h.log == nil {
		return
	}
	h.log.WarnCtx(ctx, "extraction enqueue failed; buffer retained",
		"error", err, "session_id", job.sessionID.String())
}

func (h sessionTerminateHandler) ackAfterSuccess(ctx context.Context, job terminateEnqueueJob) {
	err := h.ackTurns(ctx, job)
	if err != nil {
		h.warnAck(ctx, job, err)
	}
	h.recordEnqueue("success", "ok")
}

func (h sessionTerminateHandler) warnAck(ctx context.Context, job terminateEnqueueJob, err error) {
	if h.log == nil {
		return
	}
	h.log.WarnCtx(ctx, "extraction buffer ack failed after enqueue",
		"error", err, "external_id", job.externalID)
}

func (h sessionTerminateHandler) postEnqueue(
	ctx context.Context, job terminateEnqueueJob, turns []extractionbuffer.Turn,
) error {
	req := extractionenqueue.Request{
		OrgID: job.orgID, AgentID: job.agentID, SessionID: job.sessionID,
		Turns: toEnqueueTurns(turns),
	}
	err := h.enqueue.Enqueue(ctx, req)
	if err != nil && enqueueTransient(err) {
		return h.enqueue.Enqueue(ctx, req)
	}
	return err
}

func (h sessionTerminateHandler) bufferKey(job terminateEnqueueJob) extractionbuffer.LookupKey {
	return extractionbuffer.LookupKey{
		OrgID: job.orgID, AgentID: job.agentID, ExternalID: job.externalID,
	}
}

func (h sessionTerminateHandler) peekTurns(
	ctx context.Context, job terminateEnqueueJob,
) ([]extractionbuffer.Turn, error) {
	if h.buffer == nil {
		return nil, nil
	}
	return h.buffer.Peek(ctx, h.bufferKey(job))
}

func (h sessionTerminateHandler) ackTurns(ctx context.Context, job terminateEnqueueJob) error {
	if h.buffer == nil {
		return nil
	}
	return h.buffer.Ack(ctx, h.bufferKey(job))
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

func enqueueTransient(err error) bool {
	if err == nil {
		return false
	}
	msg := err.Error()
	// Do not retry client/auth/validation responses (4xx).
	return !strings.Contains(msg, "status 4")
}
