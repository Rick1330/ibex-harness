package chat

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
	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/packages/reqid"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	httpsession "github.com/Rick1330/ibex-harness/services/proxy/internal/http/session"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/llm"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/validation"
	"github.com/google/uuid"
)

const (
	idempotencyHeader    = "Idempotency-Key"
	maxIdempotencyKeyLen = 256
	msgInternalError     = "Internal error"
)

// Claim holds ownership or replay state for an Idempotency-Key.
// Replay=true means the caller must short-circuit and return Hit; otherwise
// the caller owns the key until Finish/FinishCapture commits or releases it.
type Claim struct {
	OrgID     uuid.UUID
	Key       string
	FP        idempotency.Fingerprint
	RequestID string
	Hit       idempotency.Record
	Replay    bool
}

// Idempotency wires Redis claim/commit/release for chat completions.
// Redis errors fail open (request proceeds without a claim) so availability
// is preferred over strict dedupe when the store is unreachable.
type Idempotency struct {
	Store         idempotency.Store
	Metrics       *metrics.ProxyRegistry
	Log           *logger.Logger
	DocsBase      string
	Timeout       time.Duration
	CommitTimeout time.Duration
}

// ParseKey validates the Idempotency-Key header.
func ParseKey(h http.Header) (key string, present bool, fieldErr *apierror.FieldError) {
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

// FingerprintRequest hashes the chat fields that must match on replay.
func FingerprintRequest(parsed *llm.ChatCompletionRequest) (idempotency.Fingerprint, error) {
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

// Resolve claims or replays an idempotency key. cont=false means a response was written.
func (id Idempotency) Resolve(
	w http.ResponseWriter,
	r *http.Request,
	parsed *llm.ChatCompletionRequest,
) (claim *Claim, cont bool) {
	key, present, fieldErr := ParseKey(r.Header)
	if !present {
		id.Metrics.IncIdempotency(metrics.IdempotencySkipped)
		return nil, true
	}
	if fieldErr != nil {
		writeValidation(validationWrite{
			w: w, r: r, docsBase: id.DocsBase,
			fields: []apierror.FieldError{*fieldErr},
		})
		return nil, false
	}
	if parsed.Stream {
		writeValidation(validationWrite{
			w: w, r: r, docsBase: id.DocsBase,
			fields: []apierror.FieldError{{
				Field: "stream", Code: "UNSUPPORTED_WITH_IDEMPOTENCY",
				Message: "Idempotency-Key requires stream=false",
			}},
			detail: "Idempotency-Key is not supported for streaming requests",
		})
		return nil, false
	}
	if id.Store == nil {
		id.Metrics.IncIdempotency(metrics.IdempotencySkipped)
		return nil, true
	}
	return id.claim(w, r, parsed, key)
}

type validationWrite struct {
	w        http.ResponseWriter
	r        *http.Request
	docsBase string
	fields   []apierror.FieldError
	detail   string
}

func writeValidation(p validationWrite) {
	apierror.WriteStatus(p.w, http.StatusBadRequest, apierror.CodeValidationError,
		"Request validation failed", reqID(p.r.Context()),
		apierror.WriteOpts{DocsBase: p.docsBase, FieldErrors: p.fields, Detail: p.detail})
}

func (id Idempotency) claim(
	w http.ResponseWriter,
	r *http.Request,
	parsed *llm.ChatCompletionRequest,
	key string,
) (*Claim, bool) {
	orgID, ok := orgIDFromAuth(r)
	if !ok {
		id.Metrics.IncIdempotency(metrics.IdempotencySkipped)
		return nil, true
	}
	fp, err := FingerprintRequest(parsed)
	if err != nil {
		apierror.WriteStatus(w, http.StatusInternalServerError, apierror.CodeInternalError,
			msgInternalError, reqID(r.Context()),
			apierror.WriteOpts{Detail: "idempotency fingerprint failed", DocsBase: id.DocsBase})
		return nil, false
	}
	out, err := id.claimWithTimeout(r.Context(), orgID, key, fp)
	if err != nil {
		id.Log.WarnCtx(r.Context(), "idempotency claim failed; fail-open",
			"org_id", orgID.String(), "key_len", len(key), "error", err.Error())
		id.Metrics.IncIdempotency(metrics.IdempotencyRedisError)
		return nil, true
	}
	return id.handleOutcome(claimOutcomeParams{
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

func (id Idempotency) claimWithTimeout(
	parent context.Context,
	orgID uuid.UUID,
	key string,
	fp idempotency.Fingerprint,
) (idempotency.Outcome, error) {
	ctx, cancel := context.WithTimeout(parent, id.Timeout)
	defer cancel()
	start := time.Now()
	out, err := id.Store.Claim(ctx, idempotency.Token{OrgID: orgID, Key: key}, fp)
	id.Metrics.ObserveIdempotencyDurationSeconds(time.Since(start).Seconds())
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

func (id Idempotency) handleOutcome(p claimOutcomeParams) (*Claim, bool) {
	base := &Claim{
		OrgID: p.orgID, Key: p.key, FP: p.fp,
		RequestID: reqID(p.r.Context()),
	}
	switch p.out.Kind {
	case idempotency.KindMiss:
		id.Metrics.IncIdempotency(metrics.IdempotencyMiss)
		return base, true
	case idempotency.KindHit:
		id.Metrics.IncIdempotency(metrics.IdempotencyHit)
		base.Hit = p.out.Record
		base.Replay = true
		return base, true
	case idempotency.KindConflict:
		id.Metrics.IncIdempotency(metrics.IdempotencyConflict)
		apierror.WriteStatus(p.w, http.StatusConflict, apierror.CodeIdempotencyKeyReuse,
			"Idempotency-Key was already used with a different request", reqID(p.r.Context()),
			apierror.WriteOpts{DocsBase: id.DocsBase})
		return nil, false
	case idempotency.KindInProgress:
		id.Metrics.IncIdempotency(metrics.IdempotencyInProgress)
		apierror.WriteStatus(p.w, http.StatusConflict, apierror.CodeIdempotencyInProgress,
			"A request with this Idempotency-Key is still in progress", reqID(p.r.Context()),
			apierror.WriteOpts{DocsBase: id.DocsBase, Detail: "retry after a short backoff"})
		return nil, false
	default:
		id.Metrics.IncIdempotency(metrics.IdempotencyRedisError)
		return nil, true
	}
}

// Replay writes a cached idempotent response body.
func Replay(w http.ResponseWriter, rec idempotency.Record) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(rec.Status)
	httpsession.WriteJSONBody(w, rec.Body)
}

// ShouldCommit reports whether status is terminal for caching.
// Transient 429 and 5xx are not cached so clients can retry the same key.
func ShouldCommit(status int) bool {
	if status == http.StatusTooManyRequests || status >= 500 {
		return false
	}
	return status >= 200 && status < 500
}

// Finish commits or releases after the provider response.
// Transient 429/5xx and oversize bodies release so clients can retry the same key.
func (id Idempotency) Finish(claim *Claim, status int, body []byte) {
	if claim == nil || id.Store == nil {
		return
	}
	if !ShouldCommit(status) {
		id.release(claim)
		return
	}
	if int64(len(body)) > validation.MaxProviderResponseBytes {
		id.release(claim)
		return
	}
	id.commit(claim, status, body)
}

// FinishCapture commits a captured response, or releases when the capture was
// capped (nil body is not treated as an empty successful body).
func (id Idempotency) FinishCapture(claim *Claim, cw *CapturingWriter) {
	if cw == nil {
		return
	}
	if cw.ExceededLimit() {
		if claim != nil && id.Store != nil {
			id.release(claim)
		}
		return
	}
	id.Finish(claim, cw.Status, cw.CapturedBody())
}

func (id Idempotency) redisOpContext(claim *Claim) (context.Context, context.CancelFunc) {
	base := context.Background()
	if claim.RequestID != "" {
		base = reqid.WithRequestID(base, claim.RequestID)
	}
	timeout := id.CommitTimeout
	if timeout <= 0 {
		timeout = CASTimeout(id.Timeout)
	}
	return context.WithTimeout(base, timeout)
}

// CASTimeout budgets WATCH+GET+MULTI retries for commit/release (off hot path).
func CASTimeout(claimBudget time.Duration) time.Duration {
	const (
		casMaxTries  = 3
		rttsPerTry   = 3
		minCASBudget = 500 * time.Millisecond
	)
	budget := claimBudget * casMaxTries * rttsPerTry
	if budget < minCASBudget {
		return minCASBudget
	}
	return budget
}

func (id Idempotency) commit(claim *Claim, status int, body []byte) {
	cctx, cancel := id.redisOpContext(claim)
	defer cancel()
	start := time.Now()
	err := id.Store.Commit(cctx, idempotency.Token{OrgID: claim.OrgID, Key: claim.Key}, idempotency.Record{
		Fingerprint: claim.FP, Status: status, Body: body,
	})
	id.Metrics.ObserveIdempotencyDurationSeconds(time.Since(start).Seconds())
	if err != nil {
		id.Log.WarnCtx(cctx, "idempotency commit failed",
			"org_id", claim.OrgID.String(), "key_len", len(claim.Key), "error", err.Error())
		id.Metrics.IncIdempotency(metrics.IdempotencyRedisError)
	}
}

func (id Idempotency) release(claim *Claim) {
	cctx, cancel := id.redisOpContext(claim)
	defer cancel()
	err := id.Store.Release(cctx, idempotency.Token{OrgID: claim.OrgID, Key: claim.Key}, claim.FP)
	if err != nil {
		id.Log.WarnCtx(cctx, "idempotency release failed",
			"org_id", claim.OrgID.String(), "key_len", len(claim.Key), "error", err.Error())
		id.Metrics.IncIdempotency(metrics.IdempotencyRedisError)
	}
}

func reqID(ctx context.Context) string {
	id, _ := reqid.FromContext(ctx)
	return id
}

// CapturingWriter records status and body while forwarding to the client.
type CapturingWriter struct {
	http.ResponseWriter
	Status int
	body   bytes.Buffer
	capped bool
}

// WriteHeader records and forwards the status code.
func (c *CapturingWriter) WriteHeader(status int) {
	c.Status = status
	c.ResponseWriter.WriteHeader(status)
}

// Write buffers (capped) and forwards bytes to the client.
func (c *CapturingWriter) Write(p []byte) (int, error) {
	if c.Status == 0 {
		c.Status = http.StatusOK
	}
	if !c.capped && int64(c.body.Len()+len(p)) <= validation.MaxProviderResponseBytes {
		_, _ = c.body.Write(p)
	} else {
		c.capped = true
		c.body.Reset()
	}
	return c.ResponseWriter.Write(p)
}

// Flush implements http.Flusher when the underlying writer supports it.
func (c *CapturingWriter) Flush() {
	if f, ok := c.ResponseWriter.(http.Flusher); ok {
		f.Flush()
	}
}

// ExceededLimit reports whether the capture was discarded for size.
func (c *CapturingWriter) ExceededLimit() bool {
	return c.capped
}

// CapturedBody returns the buffered body, or nil when capped.
func (c *CapturingWriter) CapturedBody() []byte {
	if c.capped {
		return nil
	}
	return c.body.Bytes()
}
