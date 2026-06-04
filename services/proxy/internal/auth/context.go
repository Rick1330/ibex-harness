package auth

import (
	"context"
)

type contextKey struct{}

// WithContext attaches auth result to ctx.
func WithContext(ctx context.Context, res *ValidateResult) context.Context {
	return context.WithValue(ctx, contextKey{}, res)
}

// FromContext returns auth result when middleware authenticated the request.
func FromContext(ctx context.Context) (*ValidateResult, bool) {
	res, ok := ctx.Value(contextKey{}).(*ValidateResult)
	return res, ok && res != nil
}
