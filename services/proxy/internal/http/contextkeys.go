package http

import (
	"context"
	"time"

	"github.com/Rick1330/ibex-harness/packages/reqid"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
)

type contextKey int

const (
	ctxKeyTraceID contextKey = iota + 1
	ctxKeyRequestStart
	ctxKeyErrorDocsBase
	ctxKeyAgent
)

// WithRequestID stores the request ID on the context.
func WithRequestID(ctx context.Context, id string) context.Context {
	return reqid.WithRequestID(ctx, id)
}

// RequestIDFromContext returns the request ID when present.
func RequestIDFromContext(ctx context.Context) string {
	id, _ := reqid.FromContext(ctx)
	return id
}

// WithTraceID stores the trace ID on the context.
func WithTraceID(ctx context.Context, id string) context.Context {
	return context.WithValue(ctx, ctxKeyTraceID, id)
}

// TraceIDFromContext returns the trace ID when present.
func TraceIDFromContext(ctx context.Context) string {
	if id, ok := ctx.Value(ctxKeyTraceID).(string); ok {
		return id
	}
	return ""
}

// WithRequestStart stores the request start time for response-time headers.
func WithRequestStart(ctx context.Context, start time.Time) context.Context {
	return context.WithValue(ctx, ctxKeyRequestStart, start)
}

// RequestStartFromContext returns the request start time when present.
func RequestStartFromContext(ctx context.Context) (time.Time, bool) {
	t, ok := ctx.Value(ctxKeyRequestStart).(time.Time)
	return t, ok
}

// WithErrorDocsBase stores the optional error docs URL base.
func WithErrorDocsBase(ctx context.Context, base string) context.Context {
	return context.WithValue(ctx, ctxKeyErrorDocsBase, base)
}

// ErrorDocsBaseFromContext returns the error docs base URL.
func ErrorDocsBaseFromContext(ctx context.Context) string {
	if base, ok := ctx.Value(ctxKeyErrorDocsBase).(string); ok {
		return base
	}
	return ""
}

func requestIDFromContext(ctx context.Context) string {
	return RequestIDFromContext(ctx)
}

// WithAgent stores the verified agent record on the context.
func WithAgent(ctx context.Context, rec auth.AgentRecord) context.Context {
	return context.WithValue(ctx, ctxKeyAgent, rec)
}

// AgentFromContext returns the verified agent record when agent middleware ran.
func AgentFromContext(ctx context.Context) (auth.AgentRecord, bool) {
	rec, ok := ctx.Value(ctxKeyAgent).(auth.AgentRecord)
	return rec, ok
}
