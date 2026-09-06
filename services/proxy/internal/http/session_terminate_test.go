package http

import (
	"bytes"
	"context"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/packages/permissions"
	"github.com/Rick1330/ibex-harness/packages/session"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/extractionbuffer"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/extractionenqueue"
	"github.com/alicebob/miniredis/v2"
	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
)

type terminateStoreFake struct {
	result    session.CompleteResult
	sessionID uuid.UUID
	err       error
	calls     atomic.Int32
}

func (f *terminateStoreFake) GetOrCreate(context.Context, session.GetOrCreateParams) (*session.Session, error) {
	return nil, nil
}
func (f *terminateStoreFake) AppendCheckpoint(context.Context, session.CheckpointParams) error {
	return nil
}
func (f *terminateStoreFake) Complete(context.Context, uuid.UUID, uuid.UUID) (session.CompleteResult, error) {
	return session.CompleteOK, nil
}
func (f *terminateStoreFake) CompleteByExternalID(_ context.Context, _, _ uuid.UUID, _ string) (session.CompleteResult, uuid.UUID, error) {
	f.calls.Add(1)
	return f.result, f.sessionID, f.err
}
func (f *terminateStoreFake) AbandonIdle(context.Context, session.AbandonIdleParams) (session.AbandonIdleResult, error) {
	return session.AbandonIdleResult{}, nil
}

func TestUnit_SessionTerminate_OKEnqueues(t *testing.T) {
	t.Parallel()
	runTerminateCompleteCase(t, terminateCompleteCase{
		result: session.CompleteOK, wantHits: 1, withBuffer: true, ext: "ext-ok",
	})
}

func TestUnit_SessionTerminate_NoopRecoversRetained(t *testing.T) {
	t.Parallel()
	runTerminateCompleteCase(t, terminateCompleteCase{
		result: session.CompleteNoop, wantHits: 1, withBuffer: true, ext: "ext-noop",
	})
}

func TestUnit_SessionTerminate_NoopEmptyBufferSkips(t *testing.T) {
	t.Parallel()
	runTerminateCompleteCase(t, terminateCompleteCase{
		result: session.CompleteNoop, wantHits: 0, withBuffer: false, ext: "ext-noop-empty",
	})
}

type terminateCompleteCase struct {
	result     session.CompleteResult
	wantHits   int32
	withBuffer bool
	ext        string
}

func runTerminateCompleteCase(t *testing.T, tc terminateCompleteCase) {
	t.Helper()
	org, agent, sid := uuid.New(), uuid.New(), uuid.New()
	store := &terminateStoreFake{result: tc.result, sessionID: sid}
	buf := optionalTerminateBuffer(t, optionalBufArgs{
		org: org, agent: agent, ext: tc.ext, withBuffer: tc.withBuffer,
	})
	hits, srv := startEnqueueServer(t)
	h := sessionTerminateHandler{
		store: store, buffer: buf,
		enqueue: extractionenqueue.New(extractionenqueue.Config{BaseURL: srv.URL, Token: "tok"}),
		log:     logger.Discard("t"), metrics: metrics.NewProxy("proxy-test-" + tc.ext),
	}
	req := terminateAuthedRequest(t, terminateReqParams{
		org: org, agent: agent, externalID: tc.ext, body: `{"status":"completed"}`,
	})
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("status=%d body=%s", rec.Code, rec.Body.String())
	}
	assertEnqueueHits(t, hits, tc.wantHits)
}

type optionalBufArgs struct {
	org, agent uuid.UUID
	ext        string
	withBuffer bool
}

func optionalTerminateBuffer(t *testing.T, a optionalBufArgs) *extractionbuffer.Buffer {
	t.Helper()
	if !a.withBuffer {
		return nil
	}
	buf, _ := terminateBufferAndEnqueue(t, a.org, a.agent, a.ext)
	return buf
}

func startEnqueueServer(t *testing.T) (*atomic.Int32, *httptest.Server) {
	t.Helper()
	hits := &atomic.Int32{}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		hits.Add(1)
		w.WriteHeader(http.StatusAccepted)
	}))
	t.Cleanup(srv.Close)
	return hits, srv
}

func assertEnqueueHits(t *testing.T, hits *atomic.Int32, want int32) {
	t.Helper()
	if want == 0 {
		time.Sleep(50 * time.Millisecond)
		if hits.Load() != 0 {
			t.Fatalf("expected no enqueue")
		}
		return
	}
	waitFor(t, func() bool { return hits.Load() == want })
}

func TestUnit_SessionTerminate_NotFound(t *testing.T) {
	t.Parallel()
	store := &terminateStoreFake{result: session.CompleteNotFound}
	h := sessionTerminateHandler{store: store, log: logger.Discard("t")}
	req := terminateAuthedRequest(t, terminateReqParams{
		org: uuid.New(), agent: uuid.New(), externalID: "missing", body: `{"status":"completed"}`,
	})
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusNotFound {
		t.Fatalf("status=%d", rec.Code)
	}
}

func TestUnit_SessionTerminate_EnqueueFailRetainsBuffer(t *testing.T) {
	t.Parallel()
	org, agent, sid := uuid.New(), uuid.New(), uuid.New()
	store := &terminateStoreFake{result: session.CompleteOK, sessionID: sid}
	buf, _ := terminateBufferAndEnqueue(t, org, agent, "ext-fail")
	var hits atomic.Int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		hits.Add(1)
		w.WriteHeader(http.StatusServiceUnavailable)
	}))
	t.Cleanup(srv.Close)
	h := sessionTerminateHandler{
		store: store, buffer: buf,
		enqueue: extractionenqueue.New(extractionenqueue.Config{BaseURL: srv.URL, Token: "tok"}),
		log:     logger.Discard("t"), metrics: metrics.NewProxy("proxy-test-fail"),
	}
	req := terminateAuthedRequest(t, terminateReqParams{
		org: org, agent: agent, externalID: "ext-fail", body: `{"status":"completed"}`,
	})
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("status=%d", rec.Code)
	}
	waitFor(t, func() bool { return hits.Load() >= 1 })
	snap, err := buf.Peek(context.Background(), extractionbuffer.LookupKey{
		OrgID: org, AgentID: agent, ExternalID: "ext-fail",
	})
	if err != nil {
		t.Fatal(err)
	}
	if len(snap.Turns) != 1 {
		t.Fatalf("retained turns=%d want 1", len(snap.Turns))
	}
}

func TestUnit_SessionTerminate_NoopRetryAfterFail(t *testing.T) {
	t.Parallel()
	org, agent, sid := uuid.New(), uuid.New(), uuid.New()
	store := &terminateStoreFake{result: session.CompleteOK, sessionID: sid}
	buf, _ := terminateBufferAndEnqueue(t, org, agent, "ext-retry")
	var hits atomic.Int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		n := hits.Add(1)
		if n == 1 {
			w.WriteHeader(http.StatusServiceUnavailable)
			return
		}
		w.WriteHeader(http.StatusAccepted)
	}))
	t.Cleanup(srv.Close)
	h := sessionTerminateHandler{
		store: store, buffer: buf,
		enqueue: extractionenqueue.New(extractionenqueue.Config{BaseURL: srv.URL, Token: "tok"}),
		log:     logger.Discard("t"), metrics: metrics.NewProxy("proxy-test-retry"),
	}
	first := terminateAuthedRequest(t, terminateReqParams{
		org: org, agent: agent, externalID: "ext-retry", body: `{"status":"completed"}`,
	})
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, first)
	if rec.Code != http.StatusOK {
		t.Fatalf("status=%d", rec.Code)
	}
	waitFor(t, func() bool { return hits.Load() >= 1 })
	store.result = session.CompleteNoop
	second := terminateAuthedRequest(t, terminateReqParams{
		org: org, agent: agent, externalID: "ext-retry", body: `{"status":"completed"}`,
	})
	rec2 := httptest.NewRecorder()
	h.ServeHTTP(rec2, second)
	if rec2.Code != http.StatusOK {
		t.Fatalf("status=%d", rec2.Code)
	}
	waitFor(t, func() bool { return hits.Load() >= 2 })
	waitFor(t, func() bool {
		snap, err := buf.Peek(context.Background(), extractionbuffer.LookupKey{
			OrgID: org, AgentID: agent, ExternalID: "ext-retry",
		})
		return err == nil && len(snap.Turns) == 0
	})
}

func TestUnit_SessionTerminate_EmptyBufferSkips(t *testing.T) {
	t.Parallel()
	org, agent, sid := uuid.New(), uuid.New(), uuid.New()
	store := &terminateStoreFake{result: session.CompleteOK, sessionID: sid}
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	buf, err := extractionbuffer.New(client, time.Minute)
	if err != nil {
		t.Fatal(err)
	}
	var enqueueHits atomic.Int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		enqueueHits.Add(1)
		w.WriteHeader(http.StatusAccepted)
	}))
	t.Cleanup(srv.Close)
	reg := metrics.NewProxy("proxy-test-empty")
	h := sessionTerminateHandler{
		store: store, buffer: buf,
		enqueue: extractionenqueue.New(extractionenqueue.Config{BaseURL: srv.URL, Token: "tok"}),
		log:     logger.Discard("t"), metrics: reg,
	}
	req := terminateAuthedRequest(t, terminateReqParams{
		org: org, agent: agent, externalID: "ext-empty", body: `{"status":"completed"}`,
	})
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("status=%d", rec.Code)
	}
	waitFor(t, func() bool { return enqueueHits.Load() == 0 })
	time.Sleep(30 * time.Millisecond)
	if enqueueHits.Load() != 0 {
		t.Fatal("empty buffer must skip enqueue")
	}
}

func TestUnit_SessionTerminate_ValidationAndStoreErrors(t *testing.T) {
	t.Parallel()
	org, agent := uuid.New(), uuid.New()

	t.Run("bad method", func(t *testing.T) {
		t.Parallel()
		h := sessionTerminateHandler{store: &terminateStoreFake{result: session.CompleteOK}}
		req := httptest.NewRequest(http.MethodGet, "/v1/sessions/x/terminate", nil)
		req.SetPathValue("session_id", "x")
		rec := httptest.NewRecorder()
		h.ServeHTTP(rec, req)
		if rec.Code == http.StatusOK {
			t.Fatal("expected method rejection")
		}
	})

	t.Run("missing session_id", func(t *testing.T) {
		t.Parallel()
		h := sessionTerminateHandler{store: &terminateStoreFake{result: session.CompleteOK}, log: logger.Discard("t")}
		req := terminateAuthedRequest(t, terminateReqParams{org: org, agent: agent, externalID: "x", body: `{"status":"completed"}`})
		req.SetPathValue("session_id", "")
		rec := httptest.NewRecorder()
		h.ServeHTTP(rec, req)
		if rec.Code != http.StatusBadRequest {
			t.Fatalf("status=%d", rec.Code)
		}
	})

	t.Run("missing auth", func(t *testing.T) {
		t.Parallel()
		h := sessionTerminateHandler{store: &terminateStoreFake{result: session.CompleteOK}, log: logger.Discard("t")}
		req := httptest.NewRequest(http.MethodPost, "/v1/sessions/e/terminate", bytes.NewBufferString(`{"status":"completed"}`))
		req.SetPathValue("session_id", "e")
		req.Header.Set("Content-Type", "application/json")
		rec := httptest.NewRecorder()
		h.ServeHTTP(rec, req)
		if rec.Code != http.StatusInternalServerError {
			t.Fatalf("status=%d", rec.Code)
		}
	})

	t.Run("missing agent", func(t *testing.T) {
		t.Parallel()
		h := sessionTerminateHandler{store: &terminateStoreFake{result: session.CompleteOK}, log: logger.Discard("t")}
		req := httptest.NewRequest(http.MethodPost, "/v1/sessions/e/terminate", bytes.NewBufferString(`{"status":"completed"}`))
		req.SetPathValue("session_id", "e")
		req.Header.Set("Content-Type", "application/json")
		ctx := auth.WithContext(req.Context(), &auth.ValidateResult{
			OrgID: org, Permissions: int64(permissions.SessionTerminate),
		})
		rec := httptest.NewRecorder()
		h.ServeHTTP(rec, req.WithContext(ctx))
		if rec.Code != http.StatusInternalServerError {
			t.Fatalf("status=%d", rec.Code)
		}
	})

	t.Run("bad status", func(t *testing.T) {
		t.Parallel()
		h := sessionTerminateHandler{store: &terminateStoreFake{result: session.CompleteOK}, log: logger.Discard("t")}
		req := terminateAuthedRequest(t, terminateReqParams{
			org: org, agent: agent, externalID: "e", body: `{"status":"active"}`,
		})
		rec := httptest.NewRecorder()
		h.ServeHTTP(rec, req)
		if rec.Code != http.StatusBadRequest {
			t.Fatalf("status=%d", rec.Code)
		}
	})

	t.Run("bad json", func(t *testing.T) {
		t.Parallel()
		h := sessionTerminateHandler{store: &terminateStoreFake{result: session.CompleteOK}, log: logger.Discard("t")}
		req := terminateAuthedRequest(t, terminateReqParams{
			org: org, agent: agent, externalID: "e", body: `{`,
		})
		rec := httptest.NewRecorder()
		h.ServeHTTP(rec, req)
		if rec.Code != http.StatusBadRequest {
			t.Fatalf("status=%d", rec.Code)
		}
	})

	t.Run("nil store", func(t *testing.T) {
		t.Parallel()
		h := sessionTerminateHandler{log: logger.Discard("t")}
		req := terminateAuthedRequest(t, terminateReqParams{
			org: org, agent: agent, externalID: "e", body: `{"status":"completed"}`,
		})
		rec := httptest.NewRecorder()
		h.ServeHTTP(rec, req)
		if rec.Code != http.StatusServiceUnavailable {
			t.Fatalf("status=%d", rec.Code)
		}
	})

	t.Run("store error", func(t *testing.T) {
		t.Parallel()
		h := sessionTerminateHandler{
			store: &terminateStoreFake{err: context.DeadlineExceeded},
			log:   logger.Discard("t"),
		}
		req := terminateAuthedRequest(t, terminateReqParams{
			org: org, agent: agent, externalID: "e", body: `{"status":"completed"}`,
		})
		rec := httptest.NewRecorder()
		h.ServeHTTP(rec, req)
		if rec.Code != http.StatusServiceUnavailable {
			t.Fatalf("status=%d", rec.Code)
		}
	})
}

func TestUnit_SessionTerminate_DisabledEnqueueSkips(t *testing.T) {
	t.Parallel()
	org, agent, sid := uuid.New(), uuid.New(), uuid.New()
	store := &terminateStoreFake{result: session.CompleteOK, sessionID: sid}
	buf, _ := terminateBufferAndEnqueue(t, org, agent, "ext-disabled")
	h := sessionTerminateHandler{
		store: store, buffer: buf,
		enqueue: extractionenqueue.New(extractionenqueue.Config{}),
		log:     logger.Discard("t"), metrics: metrics.NewProxy("proxy-test-disabled"),
	}
	req := terminateAuthedRequest(t, terminateReqParams{
		org: org, agent: agent, externalID: "ext-disabled", body: `{"status":"completed"}`,
	})
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("status=%d", rec.Code)
	}
	time.Sleep(80 * time.Millisecond)
	snap, err := buf.Peek(context.Background(), extractionbuffer.LookupKey{
		OrgID: org, AgentID: agent, ExternalID: "ext-disabled",
	})
	if err != nil || len(snap.Turns) != 1 {
		t.Fatalf("turns=%d err=%v", len(snap.Turns), err)
	}
}

func TestUnit_SessionTerminate_LoadSnapshotPeekError(t *testing.T) {
	t.Parallel()
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{
		Addr: mr.Addr(), MaxRetries: 0,
		DialTimeout: 50 * time.Millisecond, ReadTimeout: 50 * time.Millisecond, WriteTimeout: 50 * time.Millisecond,
	})
	buf, err := extractionbuffer.New(client, time.Minute)
	if err != nil {
		t.Fatal(err)
	}
	org, agent := uuid.New(), uuid.New()
	_, err = buf.Append(context.Background(), extractionbuffer.LookupKey{
		OrgID: org, AgentID: agent, ExternalID: "peek-err",
	}, []extractionbuffer.Turn{{TurnIndex: 0, Role: "user", Content: "x"}})
	if err != nil {
		t.Fatal(err)
	}
	mr.Close()
	h := sessionTerminateHandler{buffer: buf, log: logger.Discard("t"), metrics: metrics.NewProxy("proxy-peek-err")}
	_, ok := h.loadEnqueueSnapshot(context.Background(), terminateEnqueueJob{
		orgID: org, agentID: agent, externalID: "peek-err",
	})
	if ok {
		t.Fatal("expected peek failure")
	}
	hNil := sessionTerminateHandler{buffer: buf, metrics: metrics.NewProxy("proxy-peek-err-nil")}
	_, ok = hNil.loadEnqueueSnapshot(context.Background(), terminateEnqueueJob{
		orgID: org, agentID: agent, externalID: "peek-err",
	})
	if ok {
		t.Fatal("expected peek failure without logger")
	}
}

func TestUnit_SessionTerminate_AckAfterSuccessError(t *testing.T) {
	t.Parallel()
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{
		Addr:         mr.Addr(),
		MaxRetries:   0,
		DialTimeout:  50 * time.Millisecond,
		ReadTimeout:  50 * time.Millisecond,
		WriteTimeout: 50 * time.Millisecond,
	})
	t.Cleanup(func() { _ = client.Close() })
	buf, err := extractionbuffer.New(client, time.Minute)
	if err != nil {
		t.Fatal(err)
	}
	org, agent := uuid.New(), uuid.New()
	k := extractionbuffer.LookupKey{OrgID: org, AgentID: agent, ExternalID: "ack-err"}
	if _, err := buf.Append(context.Background(), k, []extractionbuffer.Turn{
		{TurnIndex: 0, Role: "user", Content: "x"},
	}); err != nil {
		t.Fatal(err)
	}
	snap, err := buf.Peek(context.Background(), k)
	if err != nil {
		t.Fatal(err)
	}
	mr.Close()
	h := sessionTerminateHandler{buffer: buf, log: logger.Discard("t"), metrics: metrics.NewProxy("proxy-ack-err")}
	h.ackAfterSuccess(context.Background(), terminateEnqueueJob{
		orgID: org, agentID: agent, externalID: "ack-err",
	}, snap.Raw)
}

func TestUnit_SessionTerminate_PeekFailSkips(t *testing.T) {
	t.Parallel()
	org, agent, sid := uuid.New(), uuid.New(), uuid.New()
	store := &terminateStoreFake{result: session.CompleteOK, sessionID: sid}
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{
		Addr:         mr.Addr(),
		MaxRetries:   0,
		DialTimeout:  50 * time.Millisecond,
		ReadTimeout:  50 * time.Millisecond,
		WriteTimeout: 50 * time.Millisecond,
	})
	buf, err := extractionbuffer.New(client, time.Minute)
	if err != nil {
		t.Fatal(err)
	}
	_, err = buf.Append(context.Background(), extractionbuffer.LookupKey{
		OrgID: org, AgentID: agent, ExternalID: "ext-peekfail",
	}, []extractionbuffer.Turn{{TurnIndex: 0, Role: "user", Content: "hello"}})
	if err != nil {
		t.Fatal(err)
	}
	mr.Close()
	var hits atomic.Int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		hits.Add(1)
		w.WriteHeader(http.StatusAccepted)
	}))
	t.Cleanup(srv.Close)
	h := sessionTerminateHandler{
		store: store, buffer: buf,
		enqueue: extractionenqueue.New(extractionenqueue.Config{BaseURL: srv.URL, Token: "tok"}),
		log:     logger.Discard("t"), metrics: metrics.NewProxy("proxy-test-peekfail"),
	}
	req := terminateAuthedRequest(t, terminateReqParams{
		org: org, agent: agent, externalID: "ext-peekfail", body: `{"status":"completed"}`,
	})
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("status=%d", rec.Code)
	}
	time.Sleep(150 * time.Millisecond)
	if hits.Load() != 0 {
		t.Fatal("peek failure must skip enqueue")
	}
}

func terminateAuthedRequest(t *testing.T, p terminateReqParams) *http.Request {
	t.Helper()
	req := httptest.NewRequest(http.MethodPost, "/v1/sessions/"+p.externalID+"/terminate", bytes.NewBufferString(p.body))
	req.SetPathValue("session_id", p.externalID)
	req.Header.Set("Content-Type", "application/json")
	ctx := auth.WithContext(req.Context(), &auth.ValidateResult{
		OrgID: p.org, Permissions: int64(permissions.SessionTerminate | permissions.Admin),
	})
	ctx = WithAgent(ctx, auth.AgentRecord{ID: p.agent, OrgID: p.org, Status: "active"})
	return req.WithContext(ctx)
}

type terminateReqParams struct {
	org, agent uuid.UUID
	externalID string
	body       string
}

func terminateBufferAndEnqueue(t *testing.T, org, agent uuid.UUID, ext string) (*extractionbuffer.Buffer, *httptest.Server) {
	t.Helper()
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	buf, err := extractionbuffer.New(client, time.Minute)
	if err != nil {
		t.Fatal(err)
	}
	_, err = buf.Append(context.Background(), extractionbuffer.LookupKey{
		OrgID: org, AgentID: agent, ExternalID: ext,
	}, []extractionbuffer.Turn{{TurnIndex: 0, Role: "user", Content: "hello"}})
	if err != nil {
		t.Fatal(err)
	}
	return buf, nil
}

func waitFor(t *testing.T, ok func() bool) {
	t.Helper()
	deadline := time.Now().Add(2 * time.Second)
	for time.Now().Before(deadline) {
		if ok() {
			return
		}
		time.Sleep(10 * time.Millisecond)
	}
	t.Fatal("timeout waiting for condition")
}

func TestUnit_SessionTerminate_HelpersDirect(t *testing.T) {
	t.Parallel()
	h := sessionTerminateHandler{log: logger.Discard("t"), metrics: metrics.NewProxy("proxy-helpers")}
	job := terminateEnqueueJob{externalID: "e", sessionID: uuid.New()}
	h.warnAck(context.Background(), job, context.Canceled)
	h.failEnqueue(context.Background(), job, context.Canceled)
	nilLog := sessionTerminateHandler{}
	nilLog.warnAck(context.Background(), job, context.Canceled)
	nilLog.failEnqueue(context.Background(), job, context.Canceled)
	if nilLog.enqueueReady() {
		t.Fatal("nil enqueue must be disabled")
	}
	disabled := sessionTerminateHandler{enqueue: extractionenqueue.New(extractionenqueue.Config{})}
	if disabled.enqueueReady() {
		t.Fatal("empty config must be disabled")
	}
	if err := nilLog.ackSnapshot(context.Background(), job, "raw"); err != nil {
		t.Fatal(err)
	}
	h.ackAfterSuccess(context.Background(), job, "")
}
