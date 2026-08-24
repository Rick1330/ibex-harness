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

func assertWriteJSONEnvelope(t *testing.T, rec *httptest.ResponseRecorder, want envelopeWant) {
	t.Helper()
	if rec.Code != want.status {
		t.Fatalf("status: got %d want %d", rec.Code, want.status)
	}
	var body apierror.Response
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if body.Error.Code != want.code {
		t.Fatalf("code: got %s want %s", body.Error.Code, want.code)
	}
	if body.Error.Message != want.message {
		t.Fatalf("message: got %s want %s", body.Error.Message, want.message)
	}
	if body.Error.RequestID != want.requestID {
		t.Fatalf("request_id: got %s want %s", body.Error.RequestID, want.requestID)
	}
	if body.Error.Timestamp.IsZero() {
		t.Fatal("expected non-zero timestamp")
	}
}

type envelopeWant struct {
	status    int
	code      apierror.Code
	message   string
	requestID string
}

func TestWriteJSON_envelopeFields(t *testing.T) {
	t.Parallel()
	cases := []struct {
		name      string
		status    int
		code      apierror.Code
		message   string
		detail    string
		requestID string
	}{
		{
			name:      "empty detail",
			status:    http.StatusBadRequest,
			code:      apierror.CodeValidationError,
			message:   "Request validation failed",
			detail:    "",
			requestID: "req-empty",
		},
		{
			name:      "non-empty detail",
			status:    http.StatusUnauthorized,
			code:      apierror.CodeMissingToken,
			message:   "Authorization header required",
			detail:    "Provide a valid Bearer token",
			requestID: "req-detail",
		},
		{
			name:      "known error code",
			status:    http.StatusTooManyRequests,
			code:      apierror.CodeRateLimited,
			message:   "Rate limit exceeded",
			detail:    "",
			requestID: "req-rate",
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			rec := httptest.NewRecorder()
			apierror.WriteJSON(rec, tc.status, tc.code, tc.message, tc.detail, tc.requestID)
			assertWriteJSONEnvelope(t, rec, envelopeWant{
				status:    tc.status,
				code:      tc.code,
				message:   tc.message,
				requestID: tc.requestID,
			})
		})
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
