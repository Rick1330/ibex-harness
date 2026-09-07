package http

import (
	"net/http"
	"sync"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/session"
	"github.com/google/uuid"
)

// TestUnit_SessionTerminate_ActiveStatus_NoEnqueue asserts status=active returns 400
// before Complete and never starts the terminate→enqueue goroutine (hits stay 0).
func TestUnit_SessionTerminate_ActiveStatus_NoEnqueue(t *testing.T) {
	t.Parallel()
	org, agent := uuid.New(), uuid.New()
	store := &terminateStoreFake{result: session.CompleteOK, sessionID: uuid.New()}
	buf, _ := terminateBufferAndEnqueue(t, org, agent, "ext-active")
	hits, srv := startEnqueueServer(t)
	h := newTerminateHandler(t, terminateHandlerArgs{
		store: store, buf: buf, srvURL: srv.URL, metric: "proxy-test-active",
	})
	wg := armEnqueueWait(&h)
	assertTerminateCode(t, h, terminateAuthedRequest(t, terminateReqParams{
		org: org, agent: agent, externalID: "ext-active", body: `{"status":"active"}`,
	}), http.StatusBadRequest)
	assertEnqueueNeverStarted(t, wg)
	if store.calls.Load() != 0 {
		t.Fatalf("CompleteByExternalID calls=%d want 0 (validation must fail closed)", store.calls.Load())
	}
	assertEnqueueHits(t, hits, 0)
}

// assertEnqueueNeverStarted is the defined no-call outcome for paths that must not
// spawn afterTerminateEnqueue (armEnqueueWait first). Times out if Done never fires.
func assertEnqueueNeverStarted(t *testing.T, wg *sync.WaitGroup) {
	t.Helper()
	done := make(chan struct{})
	go func() {
		wg.Wait()
		close(done)
	}()
	select {
	case <-done:
		t.Fatal("enqueue goroutine started; expected validation to reject before Complete")
	case <-time.After(100 * time.Millisecond):
	}
}
