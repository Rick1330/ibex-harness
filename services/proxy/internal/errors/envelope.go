package errors

import (
	"encoding/json"
	"net/http"
	"strings"
	"time"
)

const (
	CodeMissingToken            = "MISSING_TOKEN"
	CodeInvalidToken            = "INVALID_TOKEN"
	CodeInsufficientPermissions = "INSUFFICIENT_PERMISSIONS"
	CodeServiceDegraded         = "SERVICE_DEGRADED"
	CodeInvalidJSON             = "INVALID_JSON"
	CodeProviderNotConfigured   = "PROVIDER_NOT_CONFIGURED"
	CodePayloadTooLarge         = "PAYLOAD_TOO_LARGE"
	CodeUnsupportedMediaType    = "UNSUPPORTED_MEDIA_TYPE"
	CodeValidationError         = "VALIDATION_ERROR"
	CodeMethodNotAllowed        = "METHOD_NOT_ALLOWED"
)

// FieldError is one validation failure (API_DOCUMENTATION.md).
type FieldError struct {
	Field   string `json:"field"`
	Code    string `json:"code"`
	Message string `json:"message"`
}

// Detail is the stable error envelope.
type Detail struct {
	Code        string       `json:"code"`
	Message     string       `json:"message"`
	Detail      string       `json:"detail,omitempty"`
	DocsURL     string       `json:"docs_url,omitempty"`
	RequestID   string       `json:"request_id"`
	Timestamp   time.Time    `json:"timestamp"`
	FieldErrors []FieldError `json:"field_errors,omitempty"`
}

// Response wraps Detail per API_DOCUMENTATION.md.
type Response struct {
	Error Detail `json:"error"`
}

// WriteOpts configures optional envelope fields.
type WriteOpts struct {
	Detail      string
	DocsURL     string
	FieldErrors []FieldError
	DocsBase    string
}

// Write writes a stable error response.
func Write(w http.ResponseWriter, status int, code, message, requestID string, opts WriteOpts) {
	docsURL := opts.DocsURL
	if docsURL == "" && strings.TrimSpace(opts.DocsBase) != "" {
		base := strings.TrimRight(strings.TrimSpace(opts.DocsBase), "/")
		docsURL = base + "/errors/" + code
	}
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(Response{
		Error: Detail{
			Code:        code,
			Message:     message,
			Detail:      opts.Detail,
			DocsURL:     docsURL,
			RequestID:   requestID,
			Timestamp:   time.Now().UTC(),
			FieldErrors: opts.FieldErrors,
		},
	})
}

// WriteJSON writes a stable error response (compat wrapper).
func WriteJSON(w http.ResponseWriter, status int, code, message, detail, requestID string) {
	Write(w, status, code, message, requestID, WriteOpts{Detail: detail})
}
