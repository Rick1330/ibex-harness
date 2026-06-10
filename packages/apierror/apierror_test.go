package apierror_test

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/apierror"
	"google.golang.org/grpc/codes"
)

func TestHTTPStatus_knownCodes(t *testing.T) {
	t.Parallel()
	cases := []struct {
		code   apierror.Code
		status int
	}{
		{apierror.CodeMissingToken, http.StatusUnauthorized},
		{apierror.CodeRateLimited, http.StatusTooManyRequests},
		{apierror.CodeAuthUnavailable, http.StatusServiceUnavailable},
		{apierror.CodeProviderNotConfigured, http.StatusNotImplemented},
	}
	for _, tc := range cases {
		if got := apierror.HTTPStatus(tc.code); got != tc.status {
			t.Fatalf("%s: got %d want %d", tc.code, got, tc.status)
		}
	}
}

func TestGRPCCode_knownCodes(t *testing.T) {
	if apierror.GRPCCode(apierror.CodeMissingToken) != codes.Unauthenticated {
		t.Fatal("expected Unauthenticated")
	}
	if apierror.GRPCCode(apierror.CodeRateLimited) != codes.ResourceExhausted {
		t.Fatal("expected ResourceExhausted")
	}
}

func TestWrite_envelopeShape(t *testing.T) {
	t.Parallel()
	rec := httptest.NewRecorder()
	apierror.WriteJSON(rec, http.StatusUnauthorized, apierror.CodeMissingToken, "Authorization header required", "", "req-1")

	var body apierror.Response
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if body.Error.Code != apierror.CodeMissingToken {
		t.Fatalf("code: %s", body.Error.Code)
	}
	if body.Error.RequestID != "req-1" {
		t.Fatalf("request_id: %s", body.Error.RequestID)
	}
	if body.Error.Timestamp.IsZero() {
		t.Fatal("expected timestamp")
	}
}

func TestWrite_fieldErrorsAndDocsURL(t *testing.T) {
	t.Parallel()
	rec := httptest.NewRecorder()
	apierror.Write(rec, apierror.CodeValidationError, "Request validation failed", "req-2", apierror.WriteOpts{
		DocsBase:    "https://docs.ibexharness.com",
		FieldErrors: []apierror.FieldError{{Field: "model", Code: "REQUIRED", Message: "model is required"}},
	})
	var body apierror.Response
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if len(body.Error.FieldErrors) != 1 {
		t.Fatalf("field_errors: %+v", body.Error.FieldErrors)
	}
	if body.Error.DocsURL != "https://docs.ibexharness.com/errors/VALIDATION_ERROR" {
		t.Fatalf("docs_url: %s", body.Error.DocsURL)
	}
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("status: %d", rec.Code)
	}
}
