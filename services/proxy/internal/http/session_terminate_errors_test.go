package http

import (
	"bytes"
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/permissions"
	"github.com/Rick1330/ibex-harness/packages/session"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/google/uuid"
)

func TestUnit_SessionTerminate_NotFound(t *testing.T) {
	t.Parallel()
	h := sessionTerminateHandler{
		store: &terminateStoreFake{result: session.CompleteNotFound},
		log:   logger.Discard("t"),
	}
	assertTerminateCode(t, h, terminateAuthedRequest(t, terminateReqParams{
		org: uuid.New(), agent: uuid.New(), externalID: "missing", body: `{"status":"completed"}`,
	}), http.StatusNotFound)
}

func TestUnit_SessionTerminate_BadMethod(t *testing.T) {
	t.Parallel()
	h := sessionTerminateHandler{store: &terminateStoreFake{result: session.CompleteOK}}
	req := httptest.NewRequest(http.MethodGet, "/v1/sessions/x/terminate", nil)
	req.SetPathValue("session_id", "x")
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code == http.StatusOK {
		t.Fatal("expected method rejection")
	}
}

func TestUnit_SessionTerminate_MissingSessionID(t *testing.T) {
	t.Parallel()
	org, agent := uuid.New(), uuid.New()
	h := sessionTerminateHandler{store: &terminateStoreFake{result: session.CompleteOK}, log: logger.Discard("t")}
	req := terminateAuthedRequest(t, terminateReqParams{
		org: org, agent: agent, externalID: "x", body: `{"status":"completed"}`,
	})
	req.SetPathValue("session_id", "")
	assertTerminateCode(t, h, req, http.StatusBadRequest)
}

func TestUnit_SessionTerminate_MissingAuth(t *testing.T) {
	t.Parallel()
	h := sessionTerminateHandler{store: &terminateStoreFake{result: session.CompleteOK}, log: logger.Discard("t")}
	req := httptest.NewRequest(http.MethodPost, "/v1/sessions/e/terminate", bytes.NewBufferString(`{"status":"completed"}`))
	req.SetPathValue("session_id", "e")
	req.Header.Set("Content-Type", "application/json")
	assertTerminateCode(t, h, req, http.StatusInternalServerError)
}

func TestUnit_SessionTerminate_MissingAgent(t *testing.T) {
	t.Parallel()
	org := uuid.New()
	h := sessionTerminateHandler{store: &terminateStoreFake{result: session.CompleteOK}, log: logger.Discard("t")}
	req := httptest.NewRequest(http.MethodPost, "/v1/sessions/e/terminate", bytes.NewBufferString(`{"status":"completed"}`))
	req.SetPathValue("session_id", "e")
	req.Header.Set("Content-Type", "application/json")
	ctx := auth.WithContext(req.Context(), &auth.ValidateResult{
		OrgID: org, Permissions: int64(permissions.SessionTerminate),
	})
	assertTerminateCode(t, h, req.WithContext(ctx), http.StatusInternalServerError)
}

func TestUnit_SessionTerminate_BadStatus(t *testing.T) {
	t.Parallel()
	org, agent := uuid.New(), uuid.New()
	h := sessionTerminateHandler{store: &terminateStoreFake{result: session.CompleteOK}, log: logger.Discard("t")}
	assertTerminateCode(t, h, terminateAuthedRequest(t, terminateReqParams{
		org: org, agent: agent, externalID: "e", body: `{"status":"active"}`,
	}), http.StatusBadRequest)
}

func TestUnit_SessionTerminate_BadJSON(t *testing.T) {
	t.Parallel()
	org, agent := uuid.New(), uuid.New()
	h := sessionTerminateHandler{store: &terminateStoreFake{result: session.CompleteOK}, log: logger.Discard("t")}
	assertTerminateCode(t, h, terminateAuthedRequest(t, terminateReqParams{
		org: org, agent: agent, externalID: "e", body: `{`,
	}), http.StatusBadRequest)
}

func TestUnit_SessionTerminate_NilStore(t *testing.T) {
	t.Parallel()
	org, agent := uuid.New(), uuid.New()
	h := sessionTerminateHandler{log: logger.Discard("t")}
	assertTerminateCode(t, h, terminateAuthedRequest(t, terminateReqParams{
		org: org, agent: agent, externalID: "e", body: `{"status":"completed"}`,
	}), http.StatusServiceUnavailable)
}

func TestUnit_SessionTerminate_StoreError(t *testing.T) {
	t.Parallel()
	org, agent := uuid.New(), uuid.New()
	h := sessionTerminateHandler{
		store: &terminateStoreFake{err: context.DeadlineExceeded},
		log:   logger.Discard("t"),
	}
	assertTerminateCode(t, h, terminateAuthedRequest(t, terminateReqParams{
		org: org, agent: agent, externalID: "e", body: `{"status":"completed"}`,
	}), http.StatusServiceUnavailable)
}
