package apierror

import (
	"net/http"
	"strconv"
	"time"
)

// Error is a mapped IBEX client error ready to write as the stable envelope.
// It is not a Go error value for wrapping; use packages/provider.MapError to build it.
type Error struct {
	Code       Code
	Message    string
	Detail     string
	HTTPStatus int
	RetryAfter time.Duration
}

// WriteHTTP writes err as a JSON envelope and sets Retry-After when RetryAfter > 0.
// opts.Detail is ignored when err.Detail is non-empty (err wins).
func WriteHTTP(w http.ResponseWriter, requestID string, opts WriteOpts, err *Error) {
	if err == nil {
		return
	}
	if err.RetryAfter > 0 {
		secs := int64(err.RetryAfter.Seconds())
		if secs < 1 {
			secs = 1
		}
		w.Header().Set("Retry-After", strconv.FormatInt(secs, 10))
	}
	writeOpts := opts
	if err.Detail != "" {
		writeOpts.Detail = err.Detail
	}
	status := err.HTTPStatus
	if status == 0 {
		status = HTTPStatus(err.Code)
	}
	WriteStatus(w, status, err.Code, err.Message, requestID, writeOpts)
}
