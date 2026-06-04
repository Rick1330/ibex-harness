package errors

import (
	"encoding/json"
	"net/http"
	"time"
)

const (
	CodeMissingToken            = "MISSING_TOKEN"
	CodeInvalidToken            = "INVALID_TOKEN"
	CodeInsufficientPermissions = "INSUFFICIENT_PERMISSIONS"
	CodeServiceDegraded         = "SERVICE_DEGRADED"
	CodeInvalidJSON             = "INVALID_JSON"
	CodeProviderNotConfigured   = "PROVIDER_NOT_CONFIGURED"
)

// Detail is the stable error envelope (extended by milestone 1.2.3).
type Detail struct {
	Code      string    `json:"code"`
	Message   string    `json:"message"`
	Detail    string    `json:"detail,omitempty"`
	RequestID string    `json:"request_id"`
	Timestamp time.Time `json:"timestamp"`
}

// Response wraps Detail per API_DOCUMENTATION.md.
type Response struct {
	Error Detail `json:"error"`
}

// WriteJSON writes a stable error response.
func WriteJSON(w http.ResponseWriter, status int, code, message, detail, requestID string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(Response{
		Error: Detail{
			Code:      code,
			Message:   message,
			Detail:    detail,
			RequestID: requestID,
			Timestamp: time.Now().UTC(),
		},
	})
}
