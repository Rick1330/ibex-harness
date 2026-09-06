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
)

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
	assertTerminateCode(t, h, terminateAuthedRequest(t, terminateReqParams{
		org: org, agent: agent, externalID: "ext-disabled", body: `{"status":"completed"}`,
	}), http.StatusOK)
	time.Sleep(80 * time.Millisecond)
	snap, err := buf.Peek(context.Background(), extractionbuffer.LookupKey{
		OrgID: org, AgentID: agent, ExternalID: "ext-disabled",
	})
	if err != nil {
		t.Fatal(err)
	}
	if len(snap.Turns) != 1 {
		t.Fatalf("turns=%d want 1", len(snap.Turns))
	}
}

func TestUnit_SessionTerminate_LoadSnapshotPeekError(t *testing.T) {
	t.Parallel()
	mr := miniredis.RunT(t)
	client := shortTimeoutRedis(t, mr.Addr())
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
	if _, ok := h.loadEnqueueSnapshot(context.Background(), terminateEnqueueJob{
		orgID: org, agentID: agent, externalID: "peek-err",
	}); ok {
		t.Fatal("expected peek failure")
	}
	hNil := sessionTerminateHandler{buffer: buf, metrics: metrics.NewProxy("proxy-peek-err-nil")}
	if _, ok := hNil.loadEnqueueSnapshot(context.Background(), terminateEnqueueJob{
		orgID: org, agentID: agent, externalID: "peek-err",
	}); ok {
		t.Fatal("expected peek failure without logger")
	}
}

func TestUnit_SessionTerminate_AckAfterSuccessError(t *testing.T) {
	t.Parallel()
	mr := miniredis.RunT(t)
	client := shortTimeoutRedis(t, mr.Addr())
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
	client := shortTimeoutRedis(t, mr.Addr())
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
	assertTerminateCode(t, h, terminateAuthedRequest(t, terminateReqParams{
		org: org, agent: agent, externalID: "ext-peekfail", body: `{"status":"completed"}`,
	}), http.StatusOK)
	time.Sleep(150 * time.Millisecond)
	if hits.Load() != 0 {
		t.Fatal("peek failure must skip enqueue")
	}
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
