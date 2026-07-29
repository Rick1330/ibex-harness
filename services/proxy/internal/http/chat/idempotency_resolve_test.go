package chat

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	apierror "github.com/Rick1330/ibex-harness/packages/apierror"
	"github.com/Rick1330/ibex-harness/packages/idempotency"
	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/packages/reqid"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/llm"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/validation"
	"github.com/google/uuid"
)

func testIdempotency() Idempotency {
	return Idempotency{
		Timeout: time.Second,
		Metrics: metrics.NewProxy("t"),
		Log:     logger.Discard("t"),
	}
}

func authReq(orgID string) *http.Request {
	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", nil)
	req = req.WithContext(auth.WithContext(req.Context(), &auth.ValidateResult{OrgID: orgID}))
	return req
}

type parseKeyCase struct {
	name    string
	raw     string
	present bool
	errCode string
}

func TestUnit_ParseKey(t *testing.T) {
	t.Parallel()

	tests := []parseKeyCase{
		{name: "missing", raw: "", present: false},
		{name: "whitespace only", raw: "   ", present: false},
		{name: "valid", raw: "abc", present: true},
		{name: "too long", raw: strings.Repeat("x", maxIdempotencyKeyLen+1), present: true, errCode: "TOO_LONG"},
		{name: "rune boundary ok", raw: strings.Repeat("世", maxIdempotencyKeyLen), present: true},
	}
	for _, tc := range tests {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			h := http.Header{}
			if tc.raw != "" {
				h.Set(idempotencyHeader, tc.raw)
			}

			key, present, fieldErr := ParseKey(h)

			assertParseKey(t, tc, key, present, fieldErr)
		})
	}
}

func assertParseKey(t *testing.T, tc parseKeyCase, key string, present bool, fieldErr *apierror.FieldError) {
	t.Helper()
	if present != tc.present {
		t.Fatalf("present=%v want %v", present, tc.present)
	}
	if tc.errCode != "" {
		assertParseKeyError(t, fieldErr, tc.errCode)
		return
	}
	assertParseKeyOK(t, key, present, fieldErr)
}

func assertParseKeyError(t *testing.T, fieldErr *apierror.FieldError, wantCode string) {
	t.Helper()
	if fieldErr == nil {
		t.Fatal("expected field error")
	}
	if fieldErr.Code != wantCode {
		t.Fatalf("code=%s want %s", fieldErr.Code, wantCode)
	}
}

func assertParseKeyOK(t *testing.T, key string, present bool, fieldErr *apierror.FieldError) {
	t.Helper()
	if fieldErr != nil {
		t.Fatalf("unexpected field err: %+v", fieldErr)
	}
	if !present {
		return
	}
	if key == "" {
		t.Fatal("expected non-empty key")
	}
}

func TestUnit_FingerprintRequest(t *testing.T) {
	t.Parallel()

	temp := 0.2
	maxTok := 10
	parsed := &llm.ChatCompletionRequest{
		Model: "m", Messages: []llm.Message{{Role: "user", Content: "hi"}},
		Temperature: &temp, MaxTokens: &maxTok,
	}

	fp1, err := FingerprintRequest(parsed)
	if err != nil {
		t.Fatal(err)
	}
	if fp1 == "" {
		t.Fatal("empty fingerprint")
	}

	fp2, err := FingerprintRequest(parsed)
	if err != nil {
		t.Fatal(err)
	}
	if fp2 != fp1 {
		t.Fatalf("unstable fingerprint: %q %q", fp1, fp2)
	}

	parsed.Stream = true
	fp3, err := FingerprintRequest(parsed)
	if err != nil {
		t.Fatal(err)
	}
	if fp3 == fp1 {
		t.Fatal("stream bit must change fingerprint")
	}
}

func TestUnit_Resolve_MissingKeyContinues(t *testing.T) {
	t.Parallel()

	id := testIdempotency()
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodPost, "/", nil)

	claim, cont := id.Resolve(rec, req, &llm.ChatCompletionRequest{Model: "m"})

	assertClaimCont(t, claim, cont, false, true)
}

func TestUnit_Resolve_TooLongKeyRejects(t *testing.T) {
	t.Parallel()

	id := testIdempotency()
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodPost, "/", nil)
	req.Header.Set(idempotencyHeader, strings.Repeat("k", maxIdempotencyKeyLen+1))

	claim, cont := id.Resolve(rec, req, &llm.ChatCompletionRequest{Model: "m"})

	assertClaimCont(t, claim, cont, false, false)
	assertHTTPStatus(t, rec, http.StatusBadRequest)
}

func TestUnit_Resolve_StreamRejects(t *testing.T) {
	t.Parallel()

	id := testIdempotency()
	id.Store = idempotency.Noop()
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodPost, "/", nil)
	req.Header.Set(idempotencyHeader, "k")

	claim, cont := id.Resolve(rec, req, &llm.ChatCompletionRequest{Model: "m", Stream: true})

	assertClaimCont(t, claim, cont, false, false)
	assertHTTPStatus(t, rec, http.StatusBadRequest)
}

type outcomeCase struct {
	name       string
	kind       idempotency.Kind
	record     idempotency.Record
	wantClaim  bool
	wantCont   bool
	wantReplay bool
	wantStatus int
}

func TestUnit_HandleOutcome_Kinds(t *testing.T) {
	t.Parallel()

	id := testIdempotency()
	org := uuid.MustParse(testChatOrgID)
	req := authReq(org.String())
	tests := []outcomeCase{
		{name: "miss", kind: idempotency.KindMiss, wantClaim: true, wantCont: true},
		{
			name: "hit", kind: idempotency.KindHit,
			record:    idempotency.Record{Status: 200, Body: []byte(`{}`)},
			wantClaim: true, wantCont: true, wantReplay: true,
		},
		{name: "conflict", kind: idempotency.KindConflict, wantStatus: http.StatusConflict},
		{name: "in progress", kind: idempotency.KindInProgress, wantStatus: http.StatusConflict},
	}
	for _, tc := range tests {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			rec := httptest.NewRecorder()

			claim, cont := id.handleOutcome(claimOutcomeParams{
				w: rec, r: req, orgID: org, key: "k", fp: "fp",
				out: idempotency.Outcome{Kind: tc.kind, Record: tc.record},
			})

			assertOutcome(t, tc, claim, cont, rec.Code)
		})
	}
}

func assertOutcome(t *testing.T, tc outcomeCase, claim *Claim, cont bool, status int) {
	t.Helper()
	assertClaimPresent(t, claim, tc.wantClaim)
	if cont != tc.wantCont {
		t.Fatalf("cont=%v want %v", cont, tc.wantCont)
	}
	assertClaimReplay(t, claim, tc.wantReplay)
	if tc.wantStatus == 0 {
		return
	}
	if status != tc.wantStatus {
		t.Fatalf("status=%d want %d", status, tc.wantStatus)
	}
}

func assertClaimPresent(t *testing.T, claim *Claim, want bool) {
	t.Helper()
	got := claim != nil
	if got != want {
		t.Fatalf("claim present=%v want %v", got, want)
	}
}

func assertClaimReplay(t *testing.T, claim *Claim, want bool) {
	t.Helper()
	if claim == nil {
		if want {
			t.Fatal("expected replay claim")
		}
		return
	}
	if claim.Replay != want {
		t.Fatalf("replay=%v want %v", claim.Replay, want)
	}
}

func assertClaimCont(t *testing.T, claim *Claim, cont, wantClaim, wantCont bool) {
	t.Helper()
	assertClaimPresent(t, claim, wantClaim)
	if cont != wantCont {
		t.Fatalf("cont=%v want %v", cont, wantCont)
	}
}

func assertHTTPStatus(t *testing.T, rec *httptest.ResponseRecorder, want int) {
	t.Helper()
	if rec.Code != want {
		t.Fatalf("status=%d want %d", rec.Code, want)
	}
}

func TestUnit_Claim_RedisErrorFailOpen(t *testing.T) {
	t.Parallel()

	id := testIdempotency()
	id.Store = errIdempotencyStore{claimErr: errors.New("redis down")}
	rec := httptest.NewRecorder()
	req := authReq(testChatOrgID)

	claim, cont := id.claim(rec, req, &llm.ChatCompletionRequest{Model: "m"}, "k")

	assertClaimCont(t, claim, cont, false, true)
}

func TestUnit_Claim_MissViaStore(t *testing.T) {
	t.Parallel()

	store, _ := testRedisStore(t)
	id := newIdForStore(store)
	rec := httptest.NewRecorder()
	req := authReq(testChatOrgID)

	claim, cont := id.claim(rec, req, &llm.ChatCompletionRequest{
		Model: "m", Messages: []llm.Message{{Role: "user", Content: "hi"}},
	}, "fresh-key")

	assertClaimCont(t, claim, cont, true, true)
	assertClaimReplay(t, claim, false)
}

func TestUnit_Replay(t *testing.T) {
	t.Parallel()

	rec := httptest.NewRecorder()

	Replay(rec, idempotency.Record{Status: http.StatusCreated, Body: []byte(`{"ok":true}`)})

	assertHTTPStatus(t, rec, http.StatusCreated)
	if ct := rec.Header().Get("Content-Type"); ct != "application/json" {
		t.Fatalf("content-type=%q", ct)
	}
	if body := rec.Body.String(); body != `{"ok":true}` {
		t.Fatalf("body=%q", body)
	}
}

func TestUnit_ShouldCommit(t *testing.T) {
	t.Parallel()

	cases := []struct {
		status int
		want   bool
	}{
		{200, true}, {400, true}, {429, false}, {500, false}, {100, false},
	}
	for _, tc := range cases {
		if got := ShouldCommit(tc.status); got != tc.want {
			t.Fatalf("status %d: got %v want %v", tc.status, got, tc.want)
		}
	}
}

func TestUnit_Finish_TransientReleases(t *testing.T) {
	t.Parallel()

	store, _ := testRedisStore(t)
	id := newIdForStore(store)
	org := uuid.MustParse(testChatOrgID)
	fp := idempotency.Fingerprint("fp")
	tkn, claim := seedClaimForKey(t, claimSeed{store: store, org: org, key: "transient", fp: fp})

	id.Finish(claim, http.StatusTooManyRequests, []byte(`{}`))

	assertStoreKind(t, store, tkn, fp, idempotency.KindMiss)
}

func TestUnit_Finish_Commits(t *testing.T) {
	t.Parallel()

	store, _ := testRedisStore(t)
	id := newIdForStore(store)
	org := uuid.MustParse(testChatOrgID)
	fp := idempotency.Fingerprint("fp-commit")
	tkn, claim := seedClaimForKey(t, claimSeed{store: store, org: org, key: "commit", fp: fp})

	id.Finish(claim, http.StatusOK, []byte(`{"a":1}`))

	out := assertStoreKind(t, store, tkn, fp, idempotency.KindHit)
	if out.Record.Status != http.StatusOK {
		t.Fatalf("status=%d", out.Record.Status)
	}
	if string(out.Record.Body) != `{"a":1}` {
		t.Fatalf("body=%q", out.Record.Body)
	}
}

func assertStoreKind(
	t *testing.T,
	store idempotency.Store,
	tkn idempotency.Token,
	fp idempotency.Fingerprint,
	want idempotency.Kind,
) idempotency.Outcome {
	t.Helper()
	out, err := store.Claim(context.Background(), tkn, fp)
	if err != nil {
		t.Fatal(err)
	}
	if out.Kind != want {
		t.Fatalf("kind=%v want %v", out.Kind, want)
	}
	return out
}

func TestUnit_FinishCapture_NilAndSuccess(t *testing.T) {
	t.Parallel()

	id := testIdempotency()
	id.FinishCapture(nil, nil)

	store, _ := testRedisStore(t)
	id = newIdForStore(store)
	org := uuid.MustParse(testChatOrgID)
	fp := idempotency.Fingerprint("fp-cap")
	tkn, claim := seedClaimForKey(t, claimSeed{store: store, org: org, key: "cap-ok", fp: fp})
	cw := &CapturingWriter{ResponseWriter: httptest.NewRecorder()}
	cw.WriteHeader(http.StatusOK)
	_, _ = cw.Write([]byte(`{"ok":1}`))

	id.FinishCapture(claim, cw)

	assertStoreKind(t, store, tkn, fp, idempotency.KindHit)
}

func TestUnit_CASTimeout(t *testing.T) {
	t.Parallel()

	if got := CASTimeout(time.Millisecond); got < 500*time.Millisecond {
		t.Fatalf("got %v want >= 500ms floor", got)
	}
	if got := CASTimeout(time.Second); got < 9*time.Second {
		t.Fatalf("got %v want scaled budget", got)
	}
}

func TestUnit_RedisOpContext_UsesRequestIDAndCommitTimeout(t *testing.T) {
	t.Parallel()

	id := Idempotency{CommitTimeout: 50 * time.Millisecond, Timeout: time.Second}
	claim := &Claim{RequestID: "req-123"}

	ctx, cancel := id.redisOpContext(claim)
	defer cancel()

	got, ok := reqid.FromContext(ctx)
	if !ok {
		t.Fatal("missing request id")
	}
	if got != "req-123" {
		t.Fatalf("request id=%q", got)
	}
	deadline, ok := ctx.Deadline()
	if !ok {
		t.Fatal("missing deadline")
	}
	if time.Until(deadline) > 100*time.Millisecond {
		t.Fatal("deadline not using CommitTimeout")
	}
}

func TestUnit_CapturingWriter_Flush(t *testing.T) {
	t.Parallel()

	inner := &flushableRecorder{ResponseRecorder: httptest.NewRecorder()}
	cw := &CapturingWriter{ResponseWriter: inner}

	cw.Flush()

	if !inner.flushed {
		t.Fatal("expected flush forwarded")
	}
}

type flushableRecorder struct {
	*httptest.ResponseRecorder
	flushed bool
}

func (f *flushableRecorder) Flush() { f.flushed = true }

func TestUnit_Finish_NilStore(t *testing.T) {
	t.Parallel()

	id := Idempotency{}
	id.Finish(&Claim{OrgID: uuid.New(), Key: "k", FP: "fp"}, 200, []byte(`{}`))
}

func TestUnit_FinishCapture_CappedNilStore(t *testing.T) {
	t.Parallel()

	cw := &CapturingWriter{ResponseWriter: httptest.NewRecorder()}
	big := []byte(strings.Repeat("x", int(validation.MaxProviderResponseBytes)+1))
	_, _ = cw.Write(big)
	id := Idempotency{}
	id.FinishCapture(&Claim{OrgID: uuid.New(), Key: "k", FP: "fp"}, cw)
}
