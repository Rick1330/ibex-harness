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
