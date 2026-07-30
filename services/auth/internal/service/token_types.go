package service

import (
	"errors"
	"time"

	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"google.golang.org/protobuf/types/known/timestamppb"
)

// ErrTokenNotFound indicates a token row does not exist in org scope.
var ErrTokenNotFound = errors.New("token not found")

// CreateTokenInput is the service-layer create-token request (no proto).
type CreateTokenInput struct {
	OrgID       string
	Name        string
	Description string
	Permissions int64
	UserID      *string
	AgentID     *string
	ExpiresAt   *time.Time
	TokenType   authv1.TokenType
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

// ToProtoList maps service metadata to proto messages.
func ToProtoList(rows []TokenListItem) []*authv1.TokenMetadata {
	out := make([]*authv1.TokenMetadata, 0, len(rows))
	for _, row := range rows {
		m := &authv1.TokenMetadata{
			TokenId:     row.ID,
			Name:        row.Name,
			Prefix:      row.Prefix,
			Permissions: row.Permissions,
			CreatedAt:   timestamppb.New(row.CreatedAt.UTC()),
			IsRevoked:   row.IsRevoked,
		}
		if row.ExpiresAt != nil {
			m.ExpiresAt = timestamppb.New(row.ExpiresAt.UTC())
		}
		if row.RevokedAt != nil {
			m.RevokedAt = timestamppb.New(row.RevokedAt.UTC())
		}
		out = append(out, m)
	}
	return out
}
