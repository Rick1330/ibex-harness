package service

import (
	"errors"
	"time"
)

// ErrTokenNotFound indicates a token row does not exist in org scope.
var ErrTokenNotFound = errors.New("token not found")

// TokenType is the transport-independent token kind accepted by TokenService.
type TokenType int32

const (
	// TokenTypeUnspecified means the client omitted an explicit type (treated as PAT).
	TokenTypeUnspecified TokenType = 0
	// TokenTypePAT is a personal access token.
	TokenTypePAT TokenType = 1
)

// CreateTokenInput is the service-layer create-token request.
type CreateTokenInput struct {
	OrgID       string
	Name        string
	Description string
	Permissions int64
	UserID      *string
	AgentID     *string
	ExpiresAt   *time.Time
	TokenType   TokenType
}

// TokenListItem is a safe token metadata view without hash or sql.Null*.
type TokenListItem struct {
	ID          string
	Name        string
	Prefix      string
	Permissions int64
	ExpiresAt   *time.Time
	CreatedAt   time.Time
	RevokedAt   *time.Time
	IsRevoked   bool
}
