package http

import (
	"context"
	"net/http"
	"net/http/httptest"
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
	h := sessionTerminateHandler{
		store: store, buffer: buf,
		enqueue: extractionenqueue.New(extractionenqueue.Config{BaseURL: srv.URL, Token: "tok"}),
		log:     logger.Discard("t"), metrics: metrics.NewProxy("proxy-test-" + tc.ext),
	}
	req := terminateAuthedRequest(t, terminateReqParams{
		org: org, agent: agent, externalID: tc.ext, body: `{"status":"completed"}`,
	})
	assertTerminateCode(t, h, req, http.StatusOK)
	assertEnqueueHits(t, hits, tc.wantHits)
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
	assertTerminateCode(t, h, req, http.StatusOK)
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
	assertTerminateCode(t, h, terminateAuthedRequest(t, terminateReqParams{
		org: org, agent: agent, externalID: "ext-retry", body: `{"status":"completed"}`,
	}), http.StatusOK)
	waitFor(t, func() bool { return hits.Load() >= 1 })
	store.result = session.CompleteNoop
	assertTerminateCode(t, h, terminateAuthedRequest(t, terminateReqParams{
		org: org, agent: agent, externalID: "ext-retry", body: `{"status":"completed"}`,
	}), http.StatusOK)
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
	h := sessionTerminateHandler{
		store: store, buffer: buf,
		enqueue: extractionenqueue.New(extractionenqueue.Config{BaseURL: srv.URL, Token: "tok"}),
		log:     logger.Discard("t"), metrics: metrics.NewProxy("proxy-test-empty"),
	}
	assertTerminateCode(t, h, terminateAuthedRequest(t, terminateReqParams{
		org: org, agent: agent, externalID: "ext-empty", body: `{"status":"completed"}`,
	}), http.StatusOK)
	waitFor(t, func() bool { return enqueueHits.Load() == 0 })
	time.Sleep(30 * time.Millisecond)
	if enqueueHits.Load() != 0 {
		t.Fatal("empty buffer must skip enqueue")
	}
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
	h := sessionTerminateHandler{
		store: store, buffer: buf,
		enqueue: extractionenqueue.New(extractionenqueue.Config{BaseURL: srv.URL, Token: "tok"}),
		log:     logger.Discard("t"), metrics: metrics.NewProxy("proxy-test-" + ext),
	}
	assertTerminateCode(t, h, terminateAuthedRequest(t, terminateReqParams{
		org: org, agent: agent, externalID: ext, body: `{"status":"completed"}`,
	}), http.StatusOK)
	waitFor(t, func() bool { return hits.Load() == 1 })
	waitFor(t, func() bool {
		snap, err := buf.Peek(context.Background(), extractionbuffer.LookupKey{
			OrgID: org, AgentID: agent, ExternalID: ext,
		})
		return err == nil && len(snap.Turns) == 0
	})
	store.result = session.CompleteNoop
	assertTerminateCode(t, h, terminateAuthedRequest(t, terminateReqParams{
		org: org, agent: agent, externalID: ext, body: `{"status":"completed"}`,
	}), http.StatusOK)
	time.Sleep(80 * time.Millisecond)
	if hits.Load() != 1 {
		t.Fatalf("worker hits=%d want 1 after successful Ack then Noop", hits.Load())
	}
}
