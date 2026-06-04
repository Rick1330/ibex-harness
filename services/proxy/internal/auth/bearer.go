package auth

import (
	"context"
	"errors"
	"fmt"
	"strings"
)

var (
	// ErrMissingToken indicates a missing Authorization header.
	ErrMissingToken = errors.New("missing token")
	// ErrInvalidToken indicates the token was rejected by auth.
	ErrInvalidToken = errors.New("invalid token")
	// ErrInsufficientPermissions indicates the token lacks required permissions.
	ErrInsufficientPermissions = errors.New("insufficient permissions")
	// ErrAuthUnavailable indicates auth could not be reached or timed out.
	ErrAuthUnavailable = errors.New("auth unavailable")
)

// ValidateResult holds tenant context from a successful ValidateToken call.
type ValidateResult struct {
	OrgID       string
	Permissions int64
	AgentID     string
	UserID      string
	TokenID     string
}

// TokenValidator validates bearer tokens. A cache decorator may wrap GRPCValidator in Phase 2.
type TokenValidator interface {
	Validate(ctx context.Context, accessToken string) (*ValidateResult, error)
}

// ParseAuthorizationHeader extracts the bearer token from Authorization.
// Returns ErrMissingToken when absent; error for malformed header.
func ParseAuthorizationHeader(header string) (string, error) {
	header = strings.TrimSpace(header)
	if header == "" {
		return "", ErrMissingToken
	}
	for i := 0; i < len(header); i++ {
		if header[i] != ' ' && header[i] != '\t' {
			continue
		}
		if !strings.EqualFold(header[:i], "Bearer") {
			return "", fmt.Errorf("authorization must use Bearer scheme")
		}
		token := strings.TrimSpace(header[i+1:])
		if token == "" {
			return "", ErrMissingToken
		}
		return token, nil
	}
	if strings.EqualFold(header, "Bearer") {
		return "", ErrMissingToken
	}
	return "", fmt.Errorf("authorization must use Bearer scheme")
}
