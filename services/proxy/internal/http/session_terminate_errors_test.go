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

type terminateErrorSpec struct {
	name       string
	want       int
	body       string
	externalID string
	clearPath  bool
	nilStore   bool
	storeErr   error
	notFound   bool
	noAuth     bool
	authOnly   bool
}

func TestUnit_SessionTerminate_ErrorPaths(t *testing.T) {
	t.Parallel()
	for _, spec := range terminateErrorSpecs() {
		spec := spec
		t.Run(spec.name, func(t *testing.T) {
			t.Parallel()
			h, req := buildTerminateError(t, spec)
			assertTerminateCode(t, h, req, spec.want)
		})
	}
}

func terminateErrorSpecs() []terminateErrorSpec {
	return []terminateErrorSpec{
		{name: "not_found", want: http.StatusNotFound, body: `{"status":"completed"}`, externalID: "missing", notFound: true},
		{name: "missing_session_id", want: http.StatusBadRequest, body: `{"status":"completed"}`, externalID: "x", clearPath: true},
		{name: "missing_auth", want: http.StatusInternalServerError, body: `{"status":"completed"}`, externalID: "e", noAuth: true},
		{name: "missing_agent", want: http.StatusInternalServerError, body: `{"status":"completed"}`, externalID: "e", authOnly: true},
		{name: "bad_status", want: http.StatusBadRequest, body: `{"status":"active"}`, externalID: "e"},
		{name: "bad_json", want: http.StatusBadRequest, body: `{`, externalID: "e"},
		{name: "nil_store", want: http.StatusServiceUnavailable, body: `{"status":"completed"}`, externalID: "e", nilStore: true},
		{name: "store_error", want: http.StatusServiceUnavailable, body: `{"status":"completed"}`, externalID: "e", storeErr: context.DeadlineExceeded},
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

func buildTerminateError(t *testing.T, spec terminateErrorSpec) (sessionTerminateHandler, *http.Request) {
	t.Helper()
	h := terminateErrorHandler(spec)
	if spec.noAuth || spec.authOnly {
		return h, terminateUnauthedRequest(t, spec)
	}
	req := terminateAuthedRequest(t, terminateReqParams{
		org: uuid.New(), agent: uuid.New(), externalID: spec.externalID, body: spec.body,
	})
	if spec.clearPath {
		req.SetPathValue("session_id", "")
	}
	return h, req
}

func terminateErrorHandler(spec terminateErrorSpec) sessionTerminateHandler {
	if spec.nilStore {
		return sessionTerminateHandler{log: logger.Discard("t")}
	}
	store := &terminateStoreFake{result: session.CompleteOK, err: spec.storeErr}
	if spec.notFound {
		store.result = session.CompleteNotFound
	}
	return sessionTerminateHandler{store: store, log: logger.Discard("t")}
}

func terminateUnauthedRequest(t *testing.T, spec terminateErrorSpec) *http.Request {
	t.Helper()
	req := httptest.NewRequest(http.MethodPost, "/v1/sessions/"+spec.externalID+"/terminate", bytes.NewBufferString(spec.body))
	req.SetPathValue("session_id", spec.externalID)
	req.Header.Set("Content-Type", "application/json")
	if !spec.authOnly {
		return req
	}
	ctx := auth.WithContext(req.Context(), &auth.ValidateResult{
		OrgID: uuid.New(), Permissions: int64(permissions.SessionTerminate),
	})
	return req.WithContext(ctx)
}
