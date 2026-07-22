package apierror

import (
	"net/http"
	"strconv"
	"time"
)

// Retry-After bounds for mapped provider / rate-limit responses.
const (
	minRetryAfterSecs = int64(1)
	maxRetryAfterSecs = int64(3600) // 1 hour cap — avoids pathological upstream values
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
		secs := retryAfterSeconds(err.RetryAfter)
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

// retryAfterSeconds rounds duration up to whole seconds and clamps to [1, maxRetryAfterSecs].
func retryAfterSeconds(d time.Duration) int64 {
	secs := int64((d + time.Second - 1) / time.Second)
	if secs < minRetryAfterSecs {
		return minRetryAfterSecs
	}
	if secs > maxRetryAfterSecs {
		return maxRetryAfterSecs
	}
	return secs
}
