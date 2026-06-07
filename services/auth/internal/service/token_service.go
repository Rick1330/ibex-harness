package service

import (
	"context"
	"errors"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"github.com/Rick1330/ibex-harness/services/auth/internal/repository"
	"github.com/Rick1330/ibex-harness/services/auth/internal/token"
	"google.golang.org/protobuf/types/known/timestamppb"
)

// TokenService manages PAT creation, revocation, and listing.
type TokenService struct {
	repo   *repository.TokensRepository
	argon2 token.Argon2Params
	logger *logger.Logger
}

func NewTokenService(repo *repository.TokensRepository, argon2 token.Argon2Params, log *logger.Logger) *TokenService {
	return &TokenService{repo: repo, argon2: argon2, logger: log}
}

// CreateTokenResult holds the one-time plaintext response fields.
type CreateTokenResult struct {
	TokenID   string
	Plaintext string
	Prefix    string
	CreatedAt time.Time
}

// CreateToken generates, hashes, and persists a PAT.
func (s *TokenService) CreateToken(ctx context.Context, req *authv1.CreateTokenRequest) (CreateTokenResult, error) {
	if req.GetOrgId() == "" || req.GetName() == "" {
		return CreateTokenResult{}, ErrInvalidArgument
	}
	if req.GetType() != authv1.TokenType_TOKEN_TYPE_PAT && req.GetType() != authv1.TokenType_TOKEN_TYPE_UNSPECIFIED {
		return CreateTokenResult{}, ErrInvalidArgument
	}

	plaintext, prefix, rowID, err := token.GeneratePAT()
	if err != nil {
		return CreateTokenResult{}, err
	}
	hash, err := token.HashBearer(plaintext, s.argon2)
	if err != nil {
		return CreateTokenResult{}, err
	}

	var expiresAt *time.Time
	if req.GetExpiresAt() != nil {
		t := req.GetExpiresAt().AsTime()
		expiresAt = &t
	}

	params := repository.CreateTokenParams{
		ID:          rowID.String(),
		OrgID:       req.GetOrgId(),
		Name:        req.GetName(),
		Description: req.GetDescription(),
		Hash:        hash,
		Prefix:      prefix,
		Permissions: req.GetPermissions(),
		ExpiresAt:   expiresAt,
	}
	if req.UserId != nil {
		params.UserID = req.UserId
	}
	if req.AgentId != nil {
		params.AgentID = req.AgentId
	}

	id, err := s.repo.CreateToken(ctx, params)
	if err != nil {
		return CreateTokenResult{}, err
	}

	s.logger.InfoCtx(ctx, "token_created",
		"token_id", id,
		"org_id", req.GetOrgId(),
		"type", "pat",
		"prefix", prefix,
	)

	return CreateTokenResult{
		TokenID:   id,
		Plaintext: plaintext,
		Prefix:    prefix,
		CreatedAt: time.Now().UTC(),
	}, nil
}

// RevokeToken revokes a token in org scope.
func (s *TokenService) RevokeToken(ctx context.Context, orgID, tokenID, revokedBy string, reason *string) error {
	err := s.repo.RevokeToken(ctx, orgID, tokenID, revokedBy, reason)
	if err != nil {
		return err
	}
	s.logger.InfoCtx(ctx, "token_revoked",
		"token_id", tokenID,
		"org_id", orgID,
	)
	return nil
}

// ListTokens returns metadata rows for an org.
func (s *TokenService) ListTokens(ctx context.Context, orgID, cursor string, limit int32) ([]repository.TokenMetadata, string, error) {
	return s.repo.ListTokens(ctx, orgID, cursor, int(limit))
}

// ToProtoList maps repository metadata to proto messages.
func ToProtoList(rows []repository.TokenMetadata) []*authv1.TokenMetadata {
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
		if row.ExpiresAt.Valid {
			m.ExpiresAt = timestamppb.New(row.ExpiresAt.Time.UTC())
		}
		if row.RevokedAt.Valid {
			m.RevokedAt = timestamppb.New(row.RevokedAt.Time.UTC())
		}
		out = append(out, m)
	}
	return out
}

// ErrInvalidArgument indicates a client request validation failure.
var ErrInvalidArgument = errors.New("invalid argument")
