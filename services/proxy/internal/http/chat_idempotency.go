package http

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"net/http"
	"strings"
	"time"
	"unicode/utf8"

	apierror "github.com/Rick1330/ibex-harness/packages/apierror"
	"github.com/Rick1330/ibex-harness/packages/idempotency"
	"github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/llm"
	"github.com/google/uuid"
)

const (
	idempotencyHeader    = "Idempotency-Key"
	maxIdempotencyKeyLen = 256
)

// idempotencyClaim holds state for a request that owns (or replays) a key.
type idempotencyClaim struct {
	orgID uuid.UUID
	key   string
	fp    string
	hit   *idempotency.Record
}

func parseIdempotencyKey(h http.Header) (key string, present bool, fieldErr *apierror.FieldError) {
	raw := strings.TrimSpace(h.Get(idempotencyHeader))
	if raw == "" {
		return "", false, nil
	}
	if utf8.RuneCountInString(raw) > maxIdempotencyKeyLen {
		return "", true, &apierror.FieldError{
			Field: "header.Idempotency-Key", Code: "TOO_LONG",
			Message: "Idempotency-Key must be at most 256 characters",
		}
	}
	return raw, true, nil
}

func fingerprintChatRequest(parsed *llm.ChatCompletionRequest) (string, error) {
	payload := struct {
		Model       string        `json:"model"`
		Messages    []llm.Message `json:"messages"`
		Stream      bool          `json:"stream"`
		Temperature *float64      `json:"temperature"`
		MaxTokens   *int          `json:"max_tokens"`
	}{
		Model: parsed.Model, Messages: parsed.Messages, Stream: parsed.Stream,
		Temperature: parsed.Temperature, MaxTokens: parsed.MaxTokens,
	}
	raw, err := json.Marshal(payload)
	if err != nil {
		return "", err
	}
	sum := sha256.Sum256(raw)
	return hex.EncodeToString(sum[:]), nil
}

func (h chatCompletionHandler) resolveIdempotency(
	w http.ResponseWriter,
	r *http.Request,
	parsed *llm.ChatCompletionRequest,
) (claim *idempotencyClaim, cont bool) {
	key, present, fieldErr := parseIdempotencyKey(r.Header)
	if !present {
		h.metrics.IncIdempotency(metrics.IdempotencySkipped)
		return nil, true
	}
	if fieldErr != nil {
		apierror.WriteStatus(w, http.StatusBadRequest, apierror.CodeValidationError,
			"Request validation failed", requestIDFromContext(r.Context()),
			apierror.WriteOpts{DocsBase: h.docsBase, FieldErrors: []apierror.FieldError{*fieldErr}})
		return nil, false
	}
	if parsed.Stream {
		apierror.WriteStatus(w, http.StatusBadRequest, apierror.CodeValidationError,
			"Request validation failed", requestIDFromContext(r.Context()),
			apierror.WriteOpts{
				DocsBase: h.docsBase,
				Detail:   "Idempotency-Key is not supported for streaming requests",
				FieldErrors: []apierror.FieldError{{
					Field: "stream", Code: "UNSUPPORTED_WITH_IDEMPOTENCY",
					Message: "Idempotency-Key requires stream=false",
				}},
			})
		return nil, false
	}
	if h.idempotencyStore == nil {
		h.metrics.IncIdempotency(metrics.IdempotencySkipped)
		return nil, true
	}
	return h.claimIdempotency(w, r, parsed, key)
}

func (h chatCompletionHandler) claimIdempotency(
	w http.ResponseWriter,
	r *http.Request,
	parsed *llm.ChatCompletionRequest,
	key string,
) (*idempotencyClaim, bool) {
	res, ok := auth.FromContext(r.Context())
	if !ok {
		h.metrics.IncIdempotency(metrics.IdempotencySkipped)
		return nil, true
	}
	orgID, err := uuid.Parse(res.OrgID)
	if err != nil {
		h.metrics.IncIdempotency(metrics.IdempotencySkipped)
		return nil, true
	}
	fp, err := fingerprintChatRequest(parsed)
	if err != nil {
		requestID := requestIDFromContext(r.Context())
		apierror.WriteStatus(w, http.StatusInternalServerError, apierror.CodeInternalError,
			msgInternalError, requestID,
			apierror.WriteOpts{Detail: "idempotency fingerprint failed", DocsBase: h.docsBase})
		return nil, false
	}
	ctx, cancel := context.WithTimeout(r.Context(), h.idempotencyTimeout)
	defer cancel()
	start := time.Now()
	out, err := h.idempotencyStore.Claim(ctx, orgID, key, fp)
	h.metrics.ObserveIdempotencyDurationSeconds(time.Since(start).Seconds())
	if err != nil {
		h.log.WarnCtx(r.Context(), "idempotency claim failed; fail-open",
			"org_id", orgID.String(), "key_len", len(key), "error", err.Error())
		h.metrics.IncIdempotency(metrics.IdempotencyRedisError)
		return nil, true
	}
	return h.handleClaimOutcome(w, r, orgID, key, fp, out)
}

func (h chatCompletionHandler) handleClaimOutcome(
	w http.ResponseWriter,
	r *http.Request,
	orgID uuid.UUID,
	key, fp string,
	out idempotency.Outcome,
) (*idempotencyClaim, bool) {
	switch out.Kind {
	case idempotency.KindMiss:
		h.metrics.IncIdempotency(metrics.IdempotencyMiss)
		return &idempotencyClaim{orgID: orgID, key: key, fp: fp}, true
	case idempotency.KindHit:
		h.metrics.IncIdempotency(metrics.IdempotencyHit)
		rec := out.Record
		return &idempotencyClaim{orgID: orgID, key: key, fp: fp, hit: &rec}, true
	case idempotency.KindConflict:
		h.metrics.IncIdempotency(metrics.IdempotencyConflict)
		apierror.WriteStatus(w, http.StatusConflict, apierror.CodeIdempotencyKeyReuse,
			"Idempotency-Key was already used with a different request", requestIDFromContext(r.Context()),
			apierror.WriteOpts{DocsBase: h.docsBase})
		return nil, false
	case idempotency.KindInProgress:
		h.metrics.IncIdempotency(metrics.IdempotencyInProgress)
		apierror.WriteStatus(w, http.StatusConflict, apierror.CodeIdempotencyInProgress,
			"A request with this Idempotency-Key is still in progress", requestIDFromContext(r.Context()),
			apierror.WriteOpts{DocsBase: h.docsBase, Detail: "retry after a short backoff"})
		return nil, false
	default:
		h.metrics.IncIdempotency(metrics.IdempotencyRedisError)
		return nil, true
	}
}

func replayIdempotency(w http.ResponseWriter, rec idempotency.Record) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(rec.Status)
	//nolint:errcheck // best-effort replay; client disconnect is acceptable
	_, _ = w.Write(rec.Body)
}

func (h chatCompletionHandler) commitIdempotency(ctx context.Context, claim *idempotencyClaim, status int, body []byte) {
	if claim == nil || h.idempotencyStore == nil {
		return
	}
	cctx, cancel := context.WithTimeout(ctx, h.idempotencyTimeout)
	defer cancel()
	start := time.Now()
	err := h.idempotencyStore.Commit(cctx, claim.orgID, claim.key, idempotency.Record{
		Fingerprint: claim.fp, Status: status, Body: body,
	})
	h.metrics.ObserveIdempotencyDurationSeconds(time.Since(start).Seconds())
	if err != nil {
		h.log.WarnCtx(ctx, "idempotency commit failed",
			"org_id", claim.orgID.String(), "key_len", len(claim.key), "error", err.Error())
		h.metrics.IncIdempotency(metrics.IdempotencyRedisError)
	}
}

// capturingWriter records status and body while forwarding to the client.
type capturingWriter struct {
	http.ResponseWriter
	status int
	body   bytes.Buffer
}

func (c *capturingWriter) WriteHeader(status int) {
	c.status = status
	c.ResponseWriter.WriteHeader(status)
}

func (c *capturingWriter) Write(p []byte) (int, error) {
	if c.status == 0 {
		c.status = http.StatusOK
	}
	_, _ = c.body.Write(p)
	return c.ResponseWriter.Write(p)
}

func (c *capturingWriter) Flush() {
	flushIfSupported(c.ResponseWriter)
}
