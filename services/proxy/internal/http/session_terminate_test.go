package http

import (
	"net/http"
	"net/http/httptest"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/packages/session"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/extractionbuffer"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/extractionenqueue"
	"github.com/alicebob/miniredis/v2"
	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
)

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

func runTerminateCompleteCase(t *testing.T, tc terminateCompleteCase) {
	t.Helper()
	org, agent, sid := uuid.New(), uuid.New(), uuid.New()
	store := &terminateStoreFake{result: tc.result, sessionID: sid}
	buf := optionalTerminateBuffer(t, optionalBufArgs{
		org: org, agent: agent, ext: tc.ext, withBuffer: tc.withBuffer,
	})
	hits, srv := startEnqueueServer(t)
	h := newTerminateHandler(t, store, buf, srv.URL, "proxy-test-"+tc.ext)
	wg := armEnqueueWait(&h)
	req := terminateAuthedRequest(t, terminateReqParams{
		org: org, agent: agent, externalID: tc.ext, body: `{"status":"completed"}`,
	})
	assertTerminateCode(t, h, req, http.StatusOK)
	waitEnqueueDone(t, wg)
	assertEnqueueHits(t, hits, tc.wantHits)
}

func TestUnit_SessionTerminate_EnqueueFailRetainsBuffer(t *testing.T) {
	t.Parallel()
	runTerminateRetainBufferCase(t, retainBufferCase{
		ext: "ext-fail", statusCode: http.StatusServiceUnavailable, metric: "proxy-test-fail",
	})
}

func TestUnit_SessionTerminate_NonAcceptedDoesNotAck(t *testing.T) {
	t.Parallel()
	runTerminateRetainBufferCase(t, retainBufferCase{
		ext: "ext-200", statusCode: http.StatusOK, metric: "proxy-test-200",
	})
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
	h := newTerminateHandler(t, store, buf, srv.URL, "proxy-test-retry")
	serveTerminateOnce(t, &h, org, agent, "ext-retry")
	store.result = session.CompleteNoop
	serveTerminateOnce(t, &h, org, agent, "ext-retry")
	assertEnqueueHits(t, &hits, 2)
	assertBufferTurnCount(t, buf, org, agent, "ext-retry", 0)
}

func serveTerminateOnce(t *testing.T, h *sessionTerminateHandler, org, agent uuid.UUID, ext string) {
	t.Helper()
	wg := armEnqueueWait(h)
	assertTerminateCode(t, *h, terminateAuthedRequest(t, terminateReqParams{
		org: org, agent: agent, externalID: ext, body: `{"status":"completed"}`,
	}), http.StatusOK)
	waitEnqueueDone(t, wg)
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
	h := newTerminateHandler(t, store, buf, srv.URL, "proxy-test-empty")
	serveTerminateOnce(t, &h, org, agent, "ext-empty")
	assertEnqueueHits(t, &enqueueHits, 0)
}

// TestUnit_SessionTerminate_OKThenNoopDoesNotReenqueue proves steady-state no-duplicate-work:
// CompleteOK with buffered turns enqueues once and Acks; a later CompleteNoop with empty
// buffer must not call the worker again.
func TestUnit_SessionTerminate_OKThenNoopDoesNotReenqueue(t *testing.T) {
	t.Parallel()
	org, agent, sid := uuid.New(), uuid.New(), uuid.New()
	const ext = "ext-ok-then-noop"
	store := &terminateStoreFake{result: session.CompleteOK, sessionID: sid}
	buf, _ := terminateBufferAndEnqueue(t, org, agent, ext)
	hits, srv := startEnqueueServer(t)
	h := newTerminateHandler(t, store, buf, srv.URL, "proxy-test-"+ext)
	serveTerminateOnce(t, &h, org, agent, ext)
	assertEnqueueHits(t, hits, 1)
	assertBufferTurnCount(t, buf, org, agent, ext, 0)
	store.result = session.CompleteNoop
	serveTerminateOnce(t, &h, org, agent, ext)
	assertEnqueueHits(t, hits, 1)
}

func TestUnit_SessionTerminate_ConcurrentExactlyOneEnqueue(t *testing.T) {
	t.Parallel()
	org, agent, sid := uuid.New(), uuid.New(), uuid.New()
	const ext = "ext-concurrent"
	store := &terminateStoreFake{result: session.CompleteOK, sessionID: sid}
	buf, _ := terminateBufferAndEnqueue(t, org, agent, ext)
	var hits atomic.Int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		hits.Add(1)
		time.Sleep(40 * time.Millisecond)
		w.WriteHeader(http.StatusAccepted)
	}))
	t.Cleanup(srv.Close)
	var done sync.WaitGroup
	const n = 8
	done.Add(n)
	h := sessionTerminateHandler{
		store: store, buffer: buf,
		enqueue: extractionenqueue.New(extractionenqueue.Config{BaseURL: srv.URL, Token: "tok"}),
		log:     logger.Discard("t"), metrics: metrics.NewProxy("proxy-test-" + ext),
		enqueueFlight: newTerminateEnqueueFlight(),
		enqueueDone:   done.Done,
	}
	var start sync.WaitGroup
	start.Add(n)
	codes := make(chan int, n)
	for range n {
		go func() {
			start.Done()
			start.Wait()
			rec := httptest.NewRecorder()
			h.ServeHTTP(rec, terminateAuthedRequest(t, terminateReqParams{
				org: org, agent: agent, externalID: ext, body: `{"status":"completed"}`,
			}))
			codes <- rec.Code
		}()
	}
	waitEnqueueDone(t, &done)
	for range n {
		if code := <-codes; code != http.StatusOK {
			t.Fatalf("status=%d want 200", code)
		}
	}
	assertEnqueueHits(t, &hits, 1)
}
