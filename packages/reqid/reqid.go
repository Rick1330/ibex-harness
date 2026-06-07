// Package reqid provides request ID generation and context propagation.
//
// Request IDs are UUID v7 (RFC 9562): time-ordered, monotonically
// increasing within a millisecond, globally unique across instances.
// They are safe to expose to callers in response headers and error bodies.
package reqid

import (
	"context"
	"strings"

	"github.com/google/uuid"
)

type contextKey struct{}

// Header is the canonical HTTP header name for the request ID.
const Header = "X-Request-ID"

// GRPCMetadataKey is the gRPC metadata key for request ID propagation.
const GRPCMetadataKey = "x-request-id"

// New generates a new UUID v7 request ID.
// Falls back to UUID v4 if v7 generation fails.
func New() string {
	id, err := uuid.NewV7()
	if err != nil {
		return uuid.NewString()
	}
	return id.String()
}

// ResolveInbound returns raw when it is a valid UUID, otherwise a new ID.
func ResolveInbound(raw string) string {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return New()
	}
	if _, err := uuid.Parse(raw); err != nil {
		return New()
	}
	return raw
}

// WithRequestID returns a context with the given request ID attached.
func WithRequestID(ctx context.Context, id string) context.Context {
	return context.WithValue(ctx, contextKey{}, id)
}

// FromContext retrieves the request ID from ctx.
func FromContext(ctx context.Context) (string, bool) {
	v, ok := ctx.Value(contextKey{}).(string)
	return v, ok
}

// MustFromContext retrieves the request ID or panics.
func MustFromContext(ctx context.Context) string {
	id, ok := FromContext(ctx)
	if !ok {
		panic("reqid: request ID not in context; is RequestContextMiddleware wired?")
	}
	return id
}
