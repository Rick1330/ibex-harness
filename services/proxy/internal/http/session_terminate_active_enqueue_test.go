package http

import (
	"net/http"
	"testing"

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
	assertTerminateCode(t, h, terminateAuthedRequest(t, terminateReqParams{
		org: org, agent: agent, externalID: "ext-active", body: `{"status":"active"}`,
	}), http.StatusBadRequest)
	assertEnqueueHits(t, hits, 0)
}
