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

type terminateErrorCase struct {
	name  string
	want  int
	build func(t *testing.T) (sessionTerminateHandler, *http.Request)
}

func TestUnit_SessionTerminate_ErrorPaths(t *testing.T) {
	t.Parallel()
	for _, tc := range terminateErrorCases() {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			h, req := tc.build(t)
			assertTerminateCode(t, h, req, tc.want)
		})
	}
}

func terminateErrorCases() []terminateErrorCase {
	return []terminateErrorCase{
		{name: "not_found", want: http.StatusNotFound, build: buildNotFound},
		{name: "missing_session_id", want: http.StatusBadRequest, build: buildMissingSessionID},
		{name: "missing_auth", want: http.StatusInternalServerError, build: buildMissingAuth},
		{name: "missing_agent", want: http.StatusInternalServerError, build: buildMissingAgent},
		{name: "bad_status", want: http.StatusBadRequest, build: buildBadStatus},
		{name: "bad_json", want: http.StatusBadRequest, build: buildBadJSON},
		{name: "nil_store", want: http.StatusServiceUnavailable, build: buildNilStore},
		{name: "store_error", want: http.StatusServiceUnavailable, build: buildStoreError},
	}
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

func buildNotFound(t *testing.T) (sessionTerminateHandler, *http.Request) {
	t.Helper()
	h := sessionTerminateHandler{
		store: &terminateStoreFake{result: session.CompleteNotFound},
		log:   logger.Discard("t"),
	}
	return h, terminateAuthedRequest(t, terminateReqParams{
		org: uuid.New(), agent: uuid.New(), externalID: "missing", body: `{"status":"completed"}`,
	})
}

func buildMissingSessionID(t *testing.T) (sessionTerminateHandler, *http.Request) {
	t.Helper()
	org, agent := uuid.New(), uuid.New()
	h := sessionTerminateHandler{store: &terminateStoreFake{result: session.CompleteOK}, log: logger.Discard("t")}
	req := terminateAuthedRequest(t, terminateReqParams{
		org: org, agent: agent, externalID: "x", body: `{"status":"completed"}`,
	})
	req.SetPathValue("session_id", "")
	return h, req
}

func buildMissingAuth(t *testing.T) (sessionTerminateHandler, *http.Request) {
	t.Helper()
	h := sessionTerminateHandler{store: &terminateStoreFake{result: session.CompleteOK}, log: logger.Discard("t")}
	req := httptest.NewRequest(http.MethodPost, "/v1/sessions/e/terminate", bytes.NewBufferString(`{"status":"completed"}`))
	req.SetPathValue("session_id", "e")
	req.Header.Set("Content-Type", "application/json")
	return h, req
}

func buildMissingAgent(t *testing.T) (sessionTerminateHandler, *http.Request) {
	t.Helper()
	org := uuid.New()
	h := sessionTerminateHandler{store: &terminateStoreFake{result: session.CompleteOK}, log: logger.Discard("t")}
	req := httptest.NewRequest(http.MethodPost, "/v1/sessions/e/terminate", bytes.NewBufferString(`{"status":"completed"}`))
	req.SetPathValue("session_id", "e")
	req.Header.Set("Content-Type", "application/json")
	ctx := auth.WithContext(req.Context(), &auth.ValidateResult{
		OrgID: org, Permissions: int64(permissions.SessionTerminate),
	})
	return h, req.WithContext(ctx)
}

func buildBadStatus(t *testing.T) (sessionTerminateHandler, *http.Request) {
	t.Helper()
	org, agent := uuid.New(), uuid.New()
	h := sessionTerminateHandler{store: &terminateStoreFake{result: session.CompleteOK}, log: logger.Discard("t")}
	return h, terminateAuthedRequest(t, terminateReqParams{
		org: org, agent: agent, externalID: "e", body: `{"status":"active"}`,
	})
}

func buildBadJSON(t *testing.T) (sessionTerminateHandler, *http.Request) {
	t.Helper()
	org, agent := uuid.New(), uuid.New()
	h := sessionTerminateHandler{store: &terminateStoreFake{result: session.CompleteOK}, log: logger.Discard("t")}
	return h, terminateAuthedRequest(t, terminateReqParams{
		org: org, agent: agent, externalID: "e", body: `{`,
	})
}

func buildNilStore(t *testing.T) (sessionTerminateHandler, *http.Request) {
	t.Helper()
	org, agent := uuid.New(), uuid.New()
	return sessionTerminateHandler{log: logger.Discard("t")}, terminateAuthedRequest(t, terminateReqParams{
		org: org, agent: agent, externalID: "e", body: `{"status":"completed"}`,
	})
}

func buildStoreError(t *testing.T) (sessionTerminateHandler, *http.Request) {
	t.Helper()
	org, agent := uuid.New(), uuid.New()
	h := sessionTerminateHandler{
		store: &terminateStoreFake{err: context.DeadlineExceeded},
		log:   logger.Discard("t"),
	}
	return h, terminateAuthedRequest(t, terminateReqParams{
		org: org, agent: agent, externalID: "e", body: `{"status":"completed"}`,
	})
}
