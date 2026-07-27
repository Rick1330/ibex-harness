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
	"github.com/Rick1330/ibex-harness/packages/reqid"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/llm"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/validation"
	"github.com/google/uuid"
)

const (
	idempotencyHeader    = "Idempotency-Key"
	maxIdempotencyKeyLen = 256
)

// idempotencyClaim holds state for a request that owns (or replays) a key.
type idempotencyClaim struct {
	orgID     uuid.UUID
	key       string
	fp        idempotency.Fingerprint
	requestID string
	hit       idempotency.Record
	replay    bool
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

func fingerprintChatRequest(parsed *llm.ChatCompletionRequest) (idempotency.Fingerprint, error) {
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
	return idempotency.Fingerprint(hex.EncodeToString(sum[:])), nil
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
		writeIdempotencyValidation(idempotencyValidationWrite{
			w: w, r: r, docsBase: h.docsBase,
			fields: []apierror.FieldError{*fieldErr},
		})
		return nil, false
	}
	if parsed.Stream {
		writeIdempotencyValidation(idempotencyValidationWrite{
			w: w, r: r, docsBase: h.docsBase,
			fields: []apierror.FieldError{{
				Field: "stream", Code: "UNSUPPORTED_WITH_IDEMPOTENCY",
				Message: "Idempotency-Key requires stream=false",
			}},
			detail: "Idempotency-Key is not supported for streaming requests",
		})
		return nil, false
	}
	if h.idempotencyStore == nil {
		h.metrics.IncIdempotency(metrics.IdempotencySkipped)
		return nil, true
	}
	return h.claimIdempotency(w, r, parsed, key)
}

type idempotencyValidationWrite struct {
	w        http.ResponseWriter
	r        *http.Request
	docsBase string
	fields   []apierror.FieldError
	detail   string
}

func writeIdempotencyValidation(p idempotencyValidationWrite) {
	apierror.WriteStatus(p.w, http.StatusBadRequest, apierror.CodeValidationError,
		"Request validation failed", requestIDFromContext(p.r.Context()),
		apierror.WriteOpts{DocsBase: p.docsBase, FieldErrors: p.fields, Detail: p.detail})
}

func (h chatCompletionHandler) claimIdempotency(
	w http.ResponseWriter,
	r *http.Request,
	parsed *llm.ChatCompletionRequest,
	key string,
) (*idempotencyClaim, bool) {
	orgID, ok := orgIDFromAuth(r)
	if !ok {
		h.metrics.IncIdempotency(metrics.IdempotencySkipped)
		return nil, true
	}
	fp, err := fingerprintChatRequest(parsed)
	if err != nil {
		apierror.WriteStatus(w, http.StatusInternalServerError, apierror.CodeInternalError,
			msgInternalError, requestIDFromContext(r.Context()),
			apierror.WriteOpts{Detail: "idempotency fingerprint failed", DocsBase: h.docsBase})
		return nil, false
	}
	out, err := h.claimWithTimeout(r.Context(), orgID, key, fp)
	if err != nil {
		h.log.WarnCtx(r.Context(), "idempotency claim failed; fail-open",
			"org_id", orgID.String(), "key_len", len(key), "error", err.Error())
		h.metrics.IncIdempotency(metrics.IdempotencyRedisError)
		return nil, true
	}
	return h.handleClaimOutcome(claimOutcomeParams{
		w: w, r: r, orgID: orgID, key: key, fp: fp, out: out,
	})
}

func orgIDFromAuth(r *http.Request) (uuid.UUID, bool) {
	res, ok := auth.FromContext(r.Context())
	if !ok {
		return uuid.Nil, false
	}
	orgID, err := uuid.Parse(res.OrgID)
	if err != nil {
		return uuid.Nil, false
	}
	return orgID, true
}

func (h chatCompletionHandler) claimWithTimeout(parent context.Context, orgID uuid.UUID, key string, fp idempotency.Fingerprint) (idempotency.Outcome, error) {
	ctx, cancel := context.WithTimeout(parent, h.idempotencyTimeout)
	defer cancel()
	start := time.Now()
	out, err := h.idempotencyStore.Claim(ctx, idempotency.Token{OrgID: orgID, Key: key}, fp)
	h.metrics.ObserveIdempotencyDurationSeconds(time.Since(start).Seconds())
	return out, err
}

type claimOutcomeParams struct {
	w     http.ResponseWriter
	r     *http.Request
	orgID uuid.UUID
	key   string
	fp    idempotency.Fingerprint
	out   idempotency.Outcome
}

func (h chatCompletionHandler) handleClaimOutcome(p claimOutcomeParams) (*idempotencyClaim, bool) {
	base := &idempotencyClaim{
		orgID: p.orgID, key: p.key, fp: p.fp,
		requestID: requestIDFromContext(p.r.Context()),
	}
	switch p.out.Kind {
	case idempotency.KindMiss:
		h.metrics.IncIdempotency(metrics.IdempotencyMiss)
		return base, true
	case idempotency.KindHit:
		h.metrics.IncIdempotency(metrics.IdempotencyHit)
		base.hit = p.out.Record
		base.replay = true
		return base, true
	case idempotency.KindConflict:
		h.metrics.IncIdempotency(metrics.IdempotencyConflict)
		apierror.WriteStatus(p.w, http.StatusConflict, apierror.CodeIdempotencyKeyReuse,
			"Idempotency-Key was already used with a different request", requestIDFromContext(p.r.Context()),
			apierror.WriteOpts{DocsBase: h.docsBase})
		return nil, false
	case idempotency.KindInProgress:
		h.metrics.IncIdempotency(metrics.IdempotencyInProgress)
		apierror.WriteStatus(p.w, http.StatusConflict, apierror.CodeIdempotencyInProgress,
			"A request with this Idempotency-Key is still in progress", requestIDFromContext(p.r.Context()),
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
	// Opaque JSON passthrough (same as writeJSONBody); not an HTML response.
	writeJSONBody(w, rec.Body)
}

// shouldCommitIdempotency reports whether status is terminal for caching.
// Transient 429 and 5xx are not cached so clients can retry the same key.
func shouldCommitIdempotency(status int) bool {
	if status == http.StatusTooManyRequests || status >= 500 {
		return false
	}
	return status >= 200 && status < 500
}

func (h chatCompletionHandler) finishIdempotency(claim *idempotencyClaim, status int, body []byte) {
	if claim == nil || h.idempotencyStore == nil {
		return
	}
	if !shouldCommitIdempotency(status) {
		h.releaseIdempotency(claim)
		return
	}
	if int64(len(body)) > validation.MaxProviderResponseBytes {
		h.releaseIdempotency(claim)
		return
	}
	h.commitIdempotency(claim, status, body)
}

func (h chatCompletionHandler) redisOpContext(claim *idempotencyClaim) (context.Context, context.CancelFunc) {
	base := context.Background()
	if claim.requestID != "" {
		base = reqid.WithRequestID(base, claim.requestID)
	}
	timeout := h.idempotencyCommitTimeout
	if timeout <= 0 {
		timeout = idempotencyCASHTimeout(h.idempotencyTimeout)
	}
	return context.WithTimeout(base, timeout)
}

// idempotencyCASHTimeout budgets WATCH+GET+MULTI retries for commit/release (off hot path).
func idempotencyCASHTimeout(claimBudget time.Duration) time.Duration {
	const (
		casMaxTries   = 3
		rttsPerTry    = 3
		minCASHBudget = 500 * time.Millisecond
	)
	budget := claimBudget * casMaxTries * rttsPerTry
	if budget < minCASHBudget {
		return minCASHBudget
	}
	return budget
}

func (h chatCompletionHandler) commitIdempotency(claim *idempotencyClaim, status int, body []byte) {
	cctx, cancel := h.redisOpContext(claim)
	defer cancel()
	start := time.Now()
	err := h.idempotencyStore.Commit(cctx, idempotency.Token{OrgID: claim.orgID, Key: claim.key}, idempotency.Record{
		Fingerprint: claim.fp, Status: status, Body: body,
	})
	h.metrics.ObserveIdempotencyDurationSeconds(time.Since(start).Seconds())
	if err != nil {
		h.log.WarnCtx(cctx, "idempotency commit failed",
			"org_id", claim.orgID.String(), "key_len", len(claim.key), "error", err.Error())
		h.metrics.IncIdempotency(metrics.IdempotencyRedisError)
	}
}

func (h chatCompletionHandler) releaseIdempotency(claim *idempotencyClaim) {
	cctx, cancel := h.redisOpContext(claim)
	defer cancel()
	err := h.idempotencyStore.Release(cctx, idempotency.Token{OrgID: claim.orgID, Key: claim.key}, claim.fp)
	if err != nil {
		h.log.WarnCtx(cctx, "idempotency release failed",
			"org_id", claim.orgID.String(), "key_len", len(claim.key), "error", err.Error())
		h.metrics.IncIdempotency(metrics.IdempotencyRedisError)
	}
}

// capturingWriter records status and body while forwarding to the client.
type capturingWriter struct {
	http.ResponseWriter
	status int
	body   bytes.Buffer
	capped bool
}

func (c *capturingWriter) WriteHeader(status int) {
	c.status = status
	c.ResponseWriter.WriteHeader(status)
}

func (c *capturingWriter) Write(p []byte) (int, error) {
	if c.status == 0 {
		c.status = http.StatusOK
	}
	if !c.capped && int64(c.body.Len()+len(p)) <= validation.MaxProviderResponseBytes {
		_, _ = c.body.Write(p)
	} else {
		c.capped = true
		c.body.Reset()
	}
	return c.ResponseWriter.Write(p)
}

func (c *capturingWriter) Flush() {
	flushIfSupported(c.ResponseWriter)
}

func (c *capturingWriter) capturedBody() []byte {
	if c.capped {
		return nil
	}
	return c.body.Bytes()
}
