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

func TestUnit_SessionTerminate_NoopSkips(t *testing.T) {
	t.Parallel()
	runTerminateCompleteCase(t, terminateCompleteCase{
		result: session.CompleteNoop, wantHits: 0, withBuffer: false, ext: "ext-noop",
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
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
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
	waitFor(t, func() bool {
		turns, err := buf.Peek(context.Background(), extractionbuffer.LookupKey{
			OrgID: org, AgentID: agent, ExternalID: "ext-fail",
		})
		return err == nil && len(turns) == 1
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
