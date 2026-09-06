package http

import (
	"bytes"
	"context"
	"net/http"
	"net/http/httptest"
	"sync"
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

type terminateCompleteCase struct {
	result     session.CompleteResult
	wantHits   int32
	withBuffer bool
	ext        string
}

type optionalBufArgs struct {
	org, agent uuid.UUID
	ext        string
	withBuffer bool
}

type terminateReqParams struct {
	org, agent uuid.UUID
	externalID string
	body       string
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

// armEnqueueWait registers a completion signal fired on every afterTerminateEnqueue exit
// (including skip and error paths). Call before ServeHTTP; then waitEnqueueDone.
func armEnqueueWait(h *sessionTerminateHandler) *sync.WaitGroup {
	var wg sync.WaitGroup
	wg.Add(1)
	h.enqueueDone = wg.Done
	return &wg
}

func waitEnqueueDone(t *testing.T, wg *sync.WaitGroup) {
	t.Helper()
	done := make(chan struct{})
	go func() {
		wg.Wait()
		close(done)
	}()
	select {
	case <-done:
	case <-time.After(2 * time.Second):
		t.Fatal("timeout waiting for enqueue goroutine")
	}
}

func assertEnqueueHits(t *testing.T, hits *atomic.Int32, want int32) {
	t.Helper()
	if got := hits.Load(); got != want {
		t.Fatalf("enqueue hits=%d want %d", got, want)
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

func assertTerminateCode(t *testing.T, h sessionTerminateHandler, req *http.Request, want int) {
	t.Helper()
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code != want {
		t.Fatalf("status=%d want %d body=%s", rec.Code, want, rec.Body.String())
	}
}

type terminateHandlerArgs struct {
	store  *terminateStoreFake
	buf    *extractionbuffer.Buffer
	srvURL string
	metric string
}

func newTerminateHandler(t *testing.T, a terminateHandlerArgs) sessionTerminateHandler {
	t.Helper()
	return sessionTerminateHandler{
		store: a.store, buffer: a.buf,
		enqueue: extractionenqueue.New(extractionenqueue.Config{BaseURL: a.srvURL, Token: "tok"}),
		log:     logger.Discard("t"), metrics: metrics.NewProxy(a.metric),
		enqueueFlight: newTerminateEnqueueFlight(),
	}
}

type bufferCountArgs struct {
	buf  *extractionbuffer.Buffer
	key  extractionbuffer.LookupKey
	want int
}

func assertBufferTurnCount(t *testing.T, a bufferCountArgs) {
	t.Helper()
	snap, err := a.buf.Peek(context.Background(), a.key)
	if err != nil {
		t.Fatal(err)
	}
	if len(snap.Turns) != a.want {
		t.Fatalf("turns=%d want %d", len(snap.Turns), a.want)
	}
}

type serveOnceArgs struct {
	h          *sessionTerminateHandler
	org, agent uuid.UUID
	ext        string
}

func serveTerminateOnce(t *testing.T, a serveOnceArgs) {
	t.Helper()
	wg := armEnqueueWait(a.h)
	assertTerminateCode(t, *a.h, terminateAuthedRequest(t, terminateReqParams{
		org: a.org, agent: a.agent, externalID: a.ext, body: `{"status":"completed"}`,
	}), http.StatusOK)
	waitEnqueueDone(t, wg)
}

type retainBufferCase struct {
	ext        string
	statusCode int
	metric     string
}

func runTerminateRetainBufferCase(t *testing.T, tc retainBufferCase) {
	t.Helper()
	org, agent, sid := uuid.New(), uuid.New(), uuid.New()
	store := &terminateStoreFake{result: session.CompleteOK, sessionID: sid}
	buf, _ := terminateBufferAndEnqueue(t, org, agent, tc.ext)
	var hits atomic.Int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		hits.Add(1)
		w.WriteHeader(tc.statusCode)
	}))
	t.Cleanup(srv.Close)
	h := newTerminateHandler(t, terminateHandlerArgs{
		store: store, buf: buf, srvURL: srv.URL, metric: tc.metric,
	})
	serveTerminateOnce(t, serveOnceArgs{h: &h, org: org, agent: agent, ext: tc.ext})
	assertEnqueueHits(t, &hits, 1)
	assertBufferTurnCount(t, bufferCountArgs{
		buf: buf, key: extractionbuffer.LookupKey{OrgID: org, AgentID: agent, ExternalID: tc.ext}, want: 1,
	})
}

func shortTimeoutRedis(t *testing.T, addr string) *redis.Client {
	t.Helper()
	client := redis.NewClient(&redis.Options{
		Addr: addr, MaxRetries: 0,
		DialTimeout: 50 * time.Millisecond, ReadTimeout: 50 * time.Millisecond, WriteTimeout: 50 * time.Millisecond,
	})
	t.Cleanup(func() { _ = client.Close() })
	return client
}
