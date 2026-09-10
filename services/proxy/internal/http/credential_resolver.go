package http

import (
	"context"

	"github.com/Rick1330/ibex-harness/services/proxy/internal/credentials"
)

// CredentialResolver is the chat-path port for org BYO provider keys.
type CredentialResolver interface {
	Resolve(ctx context.Context, in credentials.ResolveInput) (credentials.Result, error)
}

// credentialResolver is an alias kept for existing field names.
type credentialResolver = CredentialResolver
