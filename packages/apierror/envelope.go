package apierror

import (
	"encoding/json"
	"net/http"
	"strings"
	"time"
)

// FieldError is one validation failure (API_DOCUMENTATION.md).
type FieldError struct {
	Field   string `json:"field"`
	Code    string `json:"code"`
	Message string `json:"message"`
}

// Detail is the stable error envelope.
type Detail struct {
	Code        Code         `json:"code"`
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

// Write writes a stable error response with the appropriate HTTP status for code.
func Write(w http.ResponseWriter, code Code, message, requestID string, opts WriteOpts) {
	WriteStatus(w, HTTPStatus(code), code, message, requestID, opts)
}

// WriteStatus writes a stable error response with an explicit HTTP status.
func WriteStatus(w http.ResponseWriter, status int, code Code, message, requestID string, opts WriteOpts) {
	docsURL := opts.DocsURL
	if docsURL == "" && strings.TrimSpace(opts.DocsBase) != "" {
		base := strings.TrimRight(strings.TrimSpace(opts.DocsBase), "/")
		docsURL = base + "/errors/" + string(code)
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
func WriteJSON(w http.ResponseWriter, status int, code Code, message, detail, requestID string) {
	WriteStatus(w, status, code, message, requestID, WriteOpts{Detail: detail})
}
