package http

import (
	"context"
	"errors"
	"mime"
	"net/http"
	"strings"
	"time"

	"github.com/google/uuid"

	"github.com/Rick1330/ibex-harness/packages/reqid"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/config"
	proxyerrors "github.com/Rick1330/ibex-harness/services/proxy/internal/errors"
	"go.opentelemetry.io/otel/trace"
)

// RequestContextMiddleware assigns request/trace IDs and request start time.
func RequestContextMiddleware(cfg config.Config) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			start := time.Now()
			requestID := reqid.ResolveInbound(r.Header.Get(cfg.RequestIDHeader))
			ctx := r.Context()
			ctx = reqid.WithRequestID(ctx, requestID)
			ctx = WithRequestStart(ctx, start)
			ctx = WithErrorDocsBase(ctx, cfg.ErrorDocsBase)
			next.ServeHTTP(w, r.WithContext(ctx))
		})
	}
}

type headerResponseWriter struct {
	http.ResponseWriter
	requestIDHeader string
	traceIDHeader   string
	requestID       string
	traceID         string
	start           time.Time
	wroteHeaders    bool
}

func (h *headerResponseWriter) WriteHeader(status int) {
	h.ensureHeaders()
	h.ResponseWriter.WriteHeader(status)
}

func (h *headerResponseWriter) Write(b []byte) (int, error) {
	h.ensureHeaders()
	return h.ResponseWriter.Write(b)
}

func (h *headerResponseWriter) ensureHeaders() {
	if h.wroteHeaders {
		return
	}
	h.wroteHeaders = true
	if h.requestID != "" {
		h.ResponseWriter.Header().Set(h.requestIDHeader, h.requestID)
	}
	if h.traceID != "" {
		h.ResponseWriter.Header().Set(h.traceIDHeader, h.traceID)
	}
	elapsed := time.Since(h.start).Milliseconds()
	h.ResponseWriter.Header().Set("X-Response-Time", formatMillis(elapsed))
}

func formatMillis(ms int64) string {
	if ms < 0 {
		ms = 0
	}
	var b [20]byte
	pos := len(b)
	if ms == 0 {
		return "0"
	}
	n := ms
	for n > 0 {
		pos--
		b[pos] = byte('0' + n%10)
		n /= 10
	}
	return string(b[pos:])
}

func traceIDFromContext(ctx context.Context) string {
	span := trace.SpanFromContext(ctx)
	sc := span.SpanContext()
	if !sc.IsValid() {
		return ""
	}
	return sc.TraceID().String()
}

// ResponseHeadersMiddleware sets IBEX response headers on every response.
func ResponseHeadersMiddleware(cfg config.Config) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			start, ok := RequestStartFromContext(r.Context())
			if !ok {
				start = time.Now()
			}
			wrapped := &headerResponseWriter{
				ResponseWriter:  w,
				requestIDHeader: cfg.RequestIDHeader,
				traceIDHeader:   cfg.TraceIDHeader,
				requestID:       RequestIDFromContext(r.Context()),
				traceID:         traceIDFromContext(r.Context()),
				start:           start,
			}
			next.ServeHTTP(wrapped, r)
		})
	}
}

// BodySizeLimitMiddleware caps the request body size (must run before reads).
func BodySizeLimitMiddleware(maxBytes int64, docsBase string) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if maxBytes <= 0 {
				next.ServeHTTP(w, r)
				return
			}
			if r.ContentLength > maxBytes {
				proxyerrors.Write(w, http.StatusRequestEntityTooLarge, proxyerrors.CodePayloadTooLarge,
					"Request body too large", requestIDFromContext(r.Context()),
					proxyerrors.WriteOpts{DocsBase: docsBase})
				return
			}
			r.Body = http.MaxBytesReader(w, r.Body, maxBytes)
			next.ServeHTTP(w, r)
		})
	}
}

// ContentTypeMiddleware requires JSON Content-Type on POST requests.
func ContentTypeMiddleware(docsBase string) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if r.Method != http.MethodPost {
				next.ServeHTTP(w, r)
				return
			}
			ct := r.Header.Get("Content-Type")
			if ct == "" || !isJSONMediaType(ct) {
				proxyerrors.Write(w, http.StatusUnsupportedMediaType, proxyerrors.CodeUnsupportedMediaType,
					"Content-Type must be application/json", requestIDFromContext(r.Context()),
					proxyerrors.WriteOpts{DocsBase: docsBase})
				return
			}
			next.ServeHTTP(w, r)
		})
	}
}

func isJSONMediaType(ct string) bool {
	mediaType, _, err := mime.ParseMediaType(ct)
	return err == nil && strings.EqualFold(mediaType, "application/json")
}

// PathOrgUUIDMiddleware validates org_id path segment before auth.
func PathOrgUUIDMiddleware(docsBase string) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			orgID := strings.TrimSpace(r.PathValue("org_id"))
			if orgID == "" {
				next.ServeHTTP(w, r)
				return
			}
			if _, err := uuid.Parse(orgID); err != nil {
				proxyerrors.Write(w, http.StatusBadRequest, proxyerrors.CodeValidationError,
					"Request validation failed", requestIDFromContext(r.Context()),
					proxyerrors.WriteOpts{
						DocsBase: docsBase,
						FieldErrors: []proxyerrors.FieldError{{
							Field:   "org_id",
							Code:    "INVALID_FORMAT",
							Message: "org_id must be a valid UUID",
						}},
					})
				return
			}
			next.ServeHTTP(w, r)
		})
	}
}

// IsMaxBytesError reports whether err is from http.MaxBytesReader.
func IsMaxBytesError(err error) bool {
	var maxErr *http.MaxBytesError
	return errors.As(err, &maxErr)
}
