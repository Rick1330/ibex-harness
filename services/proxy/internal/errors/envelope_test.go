package errors

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestWriteJSONEnvelopeShape(t *testing.T) {
	rec := httptest.NewRecorder()
	WriteJSON(rec, http.StatusUnauthorized, CodeMissingToken, "Authorization header required", "", "req-1")

	var body Response
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if body.Error.Code != CodeMissingToken {
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
	rec := httptest.NewRecorder()
	Write(rec, http.StatusBadRequest, CodeValidationError, "Request validation failed", "req-2", WriteOpts{
		DocsBase:    "https://docs.ibexharness.com",
		FieldErrors: []FieldError{{Field: "model", Code: "REQUIRED", Message: "model is required"}},
	})
	var body Response
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if len(body.Error.FieldErrors) != 1 {
		t.Fatalf("field_errors: %+v", body.Error.FieldErrors)
	}
	if body.Error.DocsURL != "https://docs.ibexharness.com/errors/VALIDATION_ERROR" {
		t.Fatalf("docs_url: %s", body.Error.DocsURL)
	}
}
