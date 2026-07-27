package http

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/idempotency"
	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/llm"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/validation"
	"github.com/google/uuid"
)

type errIdempotencyStore struct {
	claimErr   error
	commitErr  error
	releaseErr error
	claimOut   idempotency.Outcome
}

func (e errIdempotencyStore) Claim(context.Context, idempotency.Token, idempotency.Fingerprint) (idempotency.Outcome, error) {
	if e.claimErr != nil {
		return idempotency.Outcome{}, e.claimErr
	}
	return e.claimOut, nil
}

func (e errIdempotencyStore) Commit(context.Context, idempotency.Token, idempotency.Record) error {
	return e.commitErr
}

func (e errIdempotencyStore) Release(context.Context, idempotency.Token, idempotency.Fingerprint) error {
	return e.releaseErr
}

func TestUnit_OrgIDFromAuth(t *testing.T) {
	t.Parallel()
	req := httptest.NewRequest(http.MethodPost, "/", nil)
	if _, ok := orgIDFromAuth(req); ok {
		t.Fatal("expected missing auth")
	}
	req = req.WithContext(auth.WithContext(req.Context(), &auth.ValidateResult{OrgID: "not-a-uuid"}))
	if _, ok := orgIDFromAuth(req); ok {
		t.Fatal("expected invalid uuid")
	}
	org := uuid.MustParse(testChatOrgID)
	req = req.WithContext(auth.WithContext(context.Background(), &auth.ValidateResult{OrgID: org.String()}))
	got, ok := orgIDFromAuth(req)
	if !ok || got != org {
		t.Fatalf("got %v ok=%v", got, ok)
	}
}

func TestUnit_HandleClaimOutcome_Default(t *testing.T) {
	t.Parallel()
	h := chatCompletionHandler{metrics: metrics.NewProxy("t"), docsBase: "", log: logger.Discard("t")}
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodPost, "/", nil)
	claim, cont := h.handleClaimOutcome(claimOutcomeParams{
		w: rec, r: req, orgID: uuid.New(), key: "k", fp: "fp",
		out: idempotency.Outcome{Kind: idempotency.Kind(99)},
	})
	if claim != nil || !cont {
		t.Fatalf("default: claim=%v cont=%v", claim, cont)
	}
}

func TestUnit_FinishIdempotency_OversizedReleases(t *testing.T) {
	t.Parallel()
	mrStore, mr := testRedisIdempotencyStore(t)
	_ = mr
	h := chatCompletionHandler{
		idempotencyStore:   mrStore,
		idempotencyTimeout: time.Second,
		metrics:            metrics.NewProxy("t"),
		log:                logger.Discard("t"),
	}
	org := uuid.MustParse(testChatOrgID)
	tkn := idempotency.Token{OrgID: org, Key: "big"}
	claim := &idempotencyClaim{orgID: org, key: "big", fp: "fp"}
	if _, err := mrStore.Claim(context.Background(), tkn, "fp"); err != nil {
		t.Fatal(err)
	}
	body := make([]byte, validation.MaxProviderResponseBytes+1)
	h.finishIdempotency(claim, http.StatusOK, body)
	out, err := mrStore.Claim(context.Background(), tkn, "fp")
	if err != nil {
		t.Fatal(err)
	}
	if out.Kind != idempotency.KindMiss {
		t.Fatalf("after oversized release Kind=%v want Miss", out.Kind)
	}
}

func TestUnit_CommitAndRelease_ErrorPaths(t *testing.T) {
	t.Parallel()
	h := chatCompletionHandler{
		idempotencyStore: errIdempotencyStore{
			commitErr:  context.DeadlineExceeded,
			releaseErr: context.DeadlineExceeded,
		},
		idempotencyTimeout: time.Millisecond,
		metrics:            metrics.NewProxy("t"),
		log:                logger.Discard("t"),
	}
	claim := &idempotencyClaim{orgID: uuid.New(), key: "k", fp: "fp"}
	h.commitIdempotency(claim, 200, []byte(`{}`))
	h.releaseIdempotency(claim)
}

func TestUnit_ClaimIdempotency_InvalidOrgSkips(t *testing.T) {
	t.Parallel()
	h := chatCompletionHandler{
		idempotencyStore: idempotency.Noop(),
		metrics:          metrics.NewProxy("t"),
		log:              logger.Discard("t"),
	}
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodPost, "/", nil)
	req = req.WithContext(auth.WithContext(req.Context(), &auth.ValidateResult{OrgID: "bad"}))
	claim, cont := h.claimIdempotency(rec, req, &llm.ChatCompletionRequest{Model: "m"}, "k")
	if claim != nil || !cont {
		t.Fatalf("claim=%v cont=%v", claim, cont)
	}
}

func TestUnit_ResolveIdempotency_NilStore(t *testing.T) {
	t.Parallel()
	h := chatCompletionHandler{metrics: metrics.NewProxy("t"), log: logger.Discard("t")}
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodPost, "/", nil)
	req.Header.Set(idempotencyHeader, "k")
	claim, cont := h.resolveIdempotency(rec, req, &llm.ChatCompletionRequest{Model: "m"})
	if claim != nil || !cont {
		t.Fatalf("nil store: claim=%v cont=%v", claim, cont)
	}
}

func TestUnit_CapturingWriter_CapAndStatus(t *testing.T) {
	t.Parallel()
	inner := httptest.NewRecorder()
	cw := &capturingWriter{ResponseWriter: inner}
	n, err := cw.Write([]byte("hi"))
	if err != nil {
		t.Fatalf("write err=%v", err)
	}
	if n != 2 {
		t.Fatalf("write n=%d want 2", n)
	}
	if cw.status != http.StatusOK {
		t.Fatalf("status=%d want %d", cw.status, http.StatusOK)
	}
	if string(cw.capturedBody()) != "hi" {
		t.Fatalf("body=%q", cw.capturedBody())
	}
	big := []byte(strings.Repeat("x", int(validation.MaxProviderResponseBytes)))
	cw2 := &capturingWriter{ResponseWriter: httptest.NewRecorder()}
	_, _ = cw2.Write(big)
	_, _ = cw2.Write([]byte("y"))
	if !cw2.capped {
		t.Fatal("expected capped=true")
	}
	if cw2.capturedBody() != nil {
		t.Fatal("expected captured body to be nil after cap")
	}
}

func TestUnit_FinishIdempotency_NilClaim(t *testing.T) {
	t.Parallel()
	h := chatCompletionHandler{idempotencyStore: idempotency.Noop()}
	h.finishIdempotency(nil, 200, []byte(`{}`))
}
