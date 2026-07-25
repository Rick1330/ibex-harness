package http

import (
	"context"
	"time"

	"github.com/Rick1330/ibex-harness/packages/directive"
	"github.com/Rick1330/ibex-harness/packages/reqid"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
)

type contextKey int

const (
	ctxKeyTraceID contextKey = iota + 1
	ctxKeyRequestStart
	ctxKeyErrorDocsBase
	ctxKeyAgent
	ctxKeyResolvedDirective
	ctxKeyResolvedSession
	ctxKeyAuthLatencyMs
	ctxKeyDirectiveLatencyMs
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

// WithResolvedDirective stores a successfully resolved directive on the request
// context for downstream injection (2.3.3). Call only after Resolve succeeds.
func WithResolvedDirective(ctx context.Context, resolved directive.Resolved) context.Context {
	return context.WithValue(ctx, ctxKeyResolvedDirective, resolved)
}

// ResolvedDirectiveFromContext returns the resolved directive when present.
// Absence is expected on fail-open resolve errors; injection must treat missing
// as "no directive" rather than an error.
func ResolvedDirectiveFromContext(ctx context.Context) (directive.Resolved, bool) {
	resolved, ok := ctx.Value(ctxKeyResolvedDirective).(directive.Resolved)
	return resolved, ok
}

func withResolvedSession(ctx context.Context, rs resolvedSession) context.Context {
	return context.WithValue(ctx, ctxKeyResolvedSession, rs)
}

// ResolvedSessionFromContext returns the session resolved for this request.
// Lifecycle sets it after sticky external_id mint/lookup (and upgrades it when
// GetOrCreate succeeds). Absence means session features are off or sticky id
// was rejected; callers must not assume a durable SessionID is present.
func ResolvedSessionFromContext(ctx context.Context) (resolvedSession, bool) {
	rs, ok := ctx.Value(ctxKeyResolvedSession).(resolvedSession)
	return rs, ok
}

// WithAuthLatencyMs stores auth middleware wall time in milliseconds.
func WithAuthLatencyMs(ctx context.Context, ms uint16) context.Context {
	return context.WithValue(ctx, ctxKeyAuthLatencyMs, ms)
}

// AuthLatencyMsFromContext returns auth stage latency when recorded.
func AuthLatencyMsFromContext(ctx context.Context) uint16 {
	ms, _ := ctx.Value(ctxKeyAuthLatencyMs).(uint16)
	return ms
}

// WithDirectiveLatencyMs stores directive resolve wall time in milliseconds.
func WithDirectiveLatencyMs(ctx context.Context, ms uint16) context.Context {
	return context.WithValue(ctx, ctxKeyDirectiveLatencyMs, ms)
}

// DirectiveLatencyMsFromContext returns directive stage latency when recorded.
func DirectiveLatencyMsFromContext(ctx context.Context) uint16 {
	ms, _ := ctx.Value(ctxKeyDirectiveLatencyMs).(uint16)
	return ms
}
