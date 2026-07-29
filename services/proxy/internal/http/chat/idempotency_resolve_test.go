package chat

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

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

func TestUnit_ParseKey(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name    string
		raw     string
		present bool
		errCode string
	}{
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
			if present != tc.present {
				t.Fatalf("present=%v want %v", present, tc.present)
			}
			if tc.errCode == "" {
				if fieldErr != nil {
					t.Fatalf("unexpected field err: %+v", fieldErr)
				}
				if present && key == "" {
					t.Fatal("expected non-empty key")
				}
				return
			}
			if fieldErr == nil || fieldErr.Code != tc.errCode {
				t.Fatalf("fieldErr=%+v want code %s", fieldErr, tc.errCode)
			}
		})
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
	if err != nil || fp1 == "" {
		t.Fatalf("fp1=%q err=%v", fp1, err)
	}
	fp2, err := FingerprintRequest(parsed)
	if err != nil || fp2 != fp1 {
		t.Fatalf("unstable fingerprint: %q %q err=%v", fp1, fp2, err)
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

func TestUnit_Resolve_Paths(t *testing.T) {
	t.Parallel()

	t.Run("missing key continues", func(t *testing.T) {
		t.Parallel()
		id := testIdempotency()
		rec := httptest.NewRecorder()
		req := httptest.NewRequest(http.MethodPost, "/", nil)
		claim, cont := id.Resolve(rec, req, &llm.ChatCompletionRequest{Model: "m"})
		if claim != nil || !cont {
			t.Fatalf("claim=%v cont=%v", claim, cont)
		}
	})

	t.Run("too long key rejects", func(t *testing.T) {
		t.Parallel()
		id := testIdempotency()
		rec := httptest.NewRecorder()
		req := httptest.NewRequest(http.MethodPost, "/", nil)
		req.Header.Set(idempotencyHeader, strings.Repeat("k", maxIdempotencyKeyLen+1))
		claim, cont := id.Resolve(rec, req, &llm.ChatCompletionRequest{Model: "m"})
		if claim != nil || cont {
			t.Fatalf("claim=%v cont=%v", claim, cont)
		}
		if rec.Code != http.StatusBadRequest {
			t.Fatalf("status=%d", rec.Code)
		}
	})

	t.Run("stream rejects", func(t *testing.T) {
		t.Parallel()
		id := testIdempotency()
		id.Store = idempotency.Noop()
		rec := httptest.NewRecorder()
		req := httptest.NewRequest(http.MethodPost, "/", nil)
		req.Header.Set(idempotencyHeader, "k")
		claim, cont := id.Resolve(rec, req, &llm.ChatCompletionRequest{Model: "m", Stream: true})
		if claim != nil || cont {
			t.Fatalf("claim=%v cont=%v", claim, cont)
		}
		if rec.Code != http.StatusBadRequest {
			t.Fatalf("status=%d", rec.Code)
		}
	})
}

func TestUnit_HandleOutcome_Kinds(t *testing.T) {
	t.Parallel()

	id := testIdempotency()
	org := uuid.MustParse(testChatOrgID)
	req := authReq(org.String())

	t.Run("miss", func(t *testing.T) {
		t.Parallel()
		rec := httptest.NewRecorder()
		claim, cont := id.handleOutcome(claimOutcomeParams{
			w: rec, r: req, orgID: org, key: "k", fp: "fp",
			out: idempotency.Outcome{Kind: idempotency.KindMiss},
		})
		if !cont || claim == nil || claim.Replay {
			t.Fatalf("claim=%+v cont=%v", claim, cont)
		}
	})

	t.Run("hit", func(t *testing.T) {
		t.Parallel()
		rec := httptest.NewRecorder()
		claim, cont := id.handleOutcome(claimOutcomeParams{
			w: rec, r: req, orgID: org, key: "k", fp: "fp",
			out: idempotency.Outcome{
				Kind:   idempotency.KindHit,
				Record: idempotency.Record{Status: 200, Body: []byte(`{}`)},
			},
		})
		if !cont || claim == nil || !claim.Replay {
			t.Fatalf("claim=%+v cont=%v", claim, cont)
		}
	})

	t.Run("conflict", func(t *testing.T) {
		t.Parallel()
		rec := httptest.NewRecorder()
		claim, cont := id.handleOutcome(claimOutcomeParams{
			w: rec, r: req, orgID: org, key: "k", fp: "fp",
			out: idempotency.Outcome{Kind: idempotency.KindConflict},
		})
		if claim != nil || cont || rec.Code != http.StatusConflict {
			t.Fatalf("claim=%v cont=%v status=%d", claim, cont, rec.Code)
		}
	})

	t.Run("in progress", func(t *testing.T) {
		t.Parallel()
		rec := httptest.NewRecorder()
		claim, cont := id.handleOutcome(claimOutcomeParams{
			w: rec, r: req, orgID: org, key: "k", fp: "fp",
			out: idempotency.Outcome{Kind: idempotency.KindInProgress},
		})
		if claim != nil || cont || rec.Code != http.StatusConflict {
			t.Fatalf("claim=%v cont=%v status=%d", claim, cont, rec.Code)
		}
	})
}

func TestUnit_Claim_RedisErrorFailOpen(t *testing.T) {
	t.Parallel()

	id := testIdempotency()
	id.Store = errIdempotencyStore{claimErr: errors.New("redis down")}
	rec := httptest.NewRecorder()
	req := authReq(testChatOrgID)
	claim, cont := id.claim(rec, req, &llm.ChatCompletionRequest{Model: "m"}, "k")
	if claim != nil || !cont {
		t.Fatalf("claim=%v cont=%v", claim, cont)
	}
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
	if !cont || claim == nil || claim.Replay {
		t.Fatalf("claim=%+v cont=%v", claim, cont)
	}
}

func TestUnit_Replay(t *testing.T) {
	t.Parallel()

	rec := httptest.NewRecorder()
	Replay(rec, idempotency.Record{Status: http.StatusCreated, Body: []byte(`{"ok":true}`)})
	if rec.Code != http.StatusCreated {
		t.Fatalf("status=%d", rec.Code)
	}
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
	out, err := store.Claim(context.Background(), tkn, fp)
	if err != nil {
		t.Fatal(err)
	}
	if out.Kind != idempotency.KindMiss {
		t.Fatalf("kind=%v want miss", out.Kind)
	}
}

func TestUnit_Finish_Commits(t *testing.T) {
	t.Parallel()

	store, _ := testRedisStore(t)
	id := newIdForStore(store)
	org := uuid.MustParse(testChatOrgID)
	fp := idempotency.Fingerprint("fp-commit")
	tkn, claim := seedClaimForKey(t, claimSeed{store: store, org: org, key: "commit", fp: fp})
	id.Finish(claim, http.StatusOK, []byte(`{"a":1}`))
	out, err := store.Claim(context.Background(), tkn, fp)
	if err != nil {
		t.Fatal(err)
	}
	if out.Kind != idempotency.KindHit {
		t.Fatalf("kind=%v want hit", out.Kind)
	}
	if out.Record.Status != http.StatusOK || string(out.Record.Body) != `{"a":1}` {
		t.Fatalf("record=%+v", out.Record)
	}
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
	out, err := store.Claim(context.Background(), tkn, fp)
	if err != nil {
		t.Fatal(err)
	}
	if out.Kind != idempotency.KindHit {
		t.Fatalf("kind=%v want hit", out.Kind)
	}
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
	if !ok || got != "req-123" {
		t.Fatalf("request id=%q ok=%v", got, ok)
	}
	deadline, ok := ctx.Deadline()
	if !ok || time.Until(deadline) > 100*time.Millisecond {
		t.Fatalf("deadline not using CommitTimeout")
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
