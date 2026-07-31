package service

import (
	"context"
	"errors"
	"fmt"
	"sync"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/revocation"
	"github.com/Rick1330/ibex-harness/services/auth/internal/repository"
	"github.com/Rick1330/ibex-harness/services/auth/internal/token"
	"github.com/google/uuid"
)

// tokenRepo persists token rows for TokenService.
type tokenRepo interface {
	CreateToken(ctx context.Context, p repository.CreateTokenParams) (string, error)
	RevokeToken(ctx context.Context, in repository.RevokeTokenInput) error
	ListTokens(ctx context.Context, orgID, cursor string, limit int) ([]repository.TokenMetadata, string, error)
}

// TokenService manages PAT creation, revocation, and listing.
type TokenService struct {
	repo          tokenRepo
	argon2        token.Argon2Params
	logger        *logger.Logger
	publisher     revocation.Publisher
	publishWG     sync.WaitGroup
	publishCancel context.CancelFunc
	publishDone   <-chan struct{}
}

// NewTokenService constructs a TokenService. publisher may be nil (NoopPublisher).
func NewTokenService(repo tokenRepo, argon2 token.Argon2Params, log *logger.Logger, publisher revocation.Publisher) *TokenService {
	if publisher == nil {
		publisher = revocation.NoopPublisher{}
	}
	ctx, cancel := context.WithCancel(context.Background())
	return &TokenService{
		repo: repo, argon2: argon2, logger: log, publisher: publisher,
		publishCancel: cancel, publishDone: ctx.Done(),
	}
}

// CreateTokenResult holds the one-time plaintext response fields.
type CreateTokenResult struct {
	TokenID   string
	Plaintext string
	Prefix    string
	CreatedAt time.Time
}

// CreateToken validates the input, generates a secure random PAT, hashes it,
// and persists the token row. It returns ErrInvalidArgument for request
// validation failures, a wrapped error if generation or hashing fails (without
// persisting anything), and a wrapped repository error if the write fails.
// The plaintext token in the result is only available at creation time.
func (s *TokenService) CreateToken(ctx context.Context, in CreateTokenInput) (CreateTokenResult, error) {
	if err := validateCreateTokenInput(in); err != nil {
		return CreateTokenResult{}, err
	}
	plaintext, prefix, params, err := buildCreateTokenParams(in, s.argon2)
	if err != nil {
		return CreateTokenResult{}, err
	}
	return s.persistToken(ctx, params, plaintext, prefix)
}

func validateCreateTokenInput(in CreateTokenInput) error {
	if in.OrgID == "" || in.Name == "" {
		return ErrInvalidArgument
	}
	if in.TokenType != TokenTypePAT && in.TokenType != TokenTypeUnspecified {
		return ErrInvalidArgument
	}
	return nil
}

func buildCreateTokenParams(in CreateTokenInput, argon2 token.Argon2Params) (plaintext, prefix string, params repository.CreateTokenParams, err error) {
	var rowID uuid.UUID
	plaintext, prefix, rowID, err = token.GeneratePAT()
	if err != nil {
		err = fmt.Errorf("generate PAT: %w", err)
		return
	}
	hash, herr := token.HashBearer(plaintext, argon2)
	if herr != nil {
		err = fmt.Errorf("hash bearer: %w", herr)
		return
	}
	params = repository.CreateTokenParams{
		ID:          rowID.String(),
		OrgID:       in.OrgID,
		Name:        in.Name,
		Description: in.Description,
		Hash:        hash,
		Prefix:      prefix,
		Permissions: in.Permissions,
		ExpiresAt:   in.ExpiresAt,
		UserID:      in.UserID,
		AgentID:     in.AgentID,
	}
	return
}

func (s *TokenService) persistToken(ctx context.Context, params repository.CreateTokenParams, plaintext, prefix string) (CreateTokenResult, error) {
	id, err := s.repo.CreateToken(ctx, params)
	if err != nil {
		return CreateTokenResult{}, fmt.Errorf("create token org_id=%s: %w", params.OrgID, err)
	}
	s.logger.InfoCtx(ctx, "token_created",
		"token_id", id,
		"org_id", params.OrgID,
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

// RevokeTokenParams scopes a durable revoke plus optional async pub/sub publish.
type RevokeTokenParams struct {
	OrgID     string
	TokenID   string
	RevokedBy string
	Reason    *string
}

// RevokeToken revokes a token in org scope, then best-effort publishes a pub/sub event.
func (s *TokenService) RevokeToken(ctx context.Context, p RevokeTokenParams) error {
	err := s.repo.RevokeToken(ctx, repository.RevokeTokenInput{
		OrgID: p.OrgID, TokenID: p.TokenID, RevokedBy: p.RevokedBy, Reason: p.Reason,
	})
	if err != nil {
		if errors.Is(err, repository.ErrNotFound) {
			return ErrTokenNotFound
		}
		return fmt.Errorf("RevokeToken org_id=%s token_id=%s: %w", p.OrgID, p.TokenID, err)
	}
	s.logger.InfoCtx(ctx, "token_revoked",
		"token_id", p.TokenID,
		"org_id", p.OrgID,
	)
	s.publishRevocationAsync(p)
	return nil
}

func (s *TokenService) publishRevocationAsync(p RevokeTokenParams) {
	s.publishWG.Add(1)
	go func() {
		defer s.publishWG.Done()
		ctx, cancel := s.newPublishContext()
		defer cancel()
		defer func() {
			if rec := recover(); rec != nil {
				s.logger.WarnCtx(ctx, "revocation publish panic recovered",
					"recover", rec, "token_id", p.TokenID)
			}
		}()
		event := revocation.RevocationEvent{
			Version:   revocation.CurrentSchemaVersion,
			TokenID:   p.TokenID,
			OrgID:     p.OrgID,
			RevokedAt: time.Now().UTC(),
		}
		if err := s.publisher.Publish(ctx, event); err != nil {
			s.logger.WarnCtx(ctx, "revocation event publish failed; LRU will expire naturally",
				"error", err, "token_id", p.TokenID, "org_id", p.OrgID)
		}
	}()
}

// newPublishContext returns a timeout context that also cancels on DrainPublishes.
func (s *TokenService) newPublishContext() (context.Context, context.CancelFunc) {
	ctx, cancel := context.WithTimeout(context.Background(), revocation.PublishTimeout)
	go s.cancelOnDrain(ctx, cancel)
	return ctx, cancel
}

func (s *TokenService) cancelOnDrain(ctx context.Context, cancel context.CancelFunc) {
	select {
	case <-s.publishDone:
		cancel()
	case <-ctx.Done():
	}
}

// WaitPendingPublishes blocks until in-flight revocation publishes finish.
func (s *TokenService) WaitPendingPublishes() {
	s.publishWG.Wait()
}

// DrainPublishes cancels the service publish context and waits for in-flight
// revocation publishes to finish. Call before closing Redis on shutdown.
func (s *TokenService) DrainPublishes() {
	s.publishCancel()
	s.publishWG.Wait()
}

// ListTokens returns metadata rows for an org.
func (s *TokenService) ListTokens(ctx context.Context, orgID, cursor string, limit int32) ([]TokenListItem, string, error) {
	rows, next, err := s.repo.ListTokens(ctx, orgID, cursor, int(limit))
	if err != nil {
		return nil, "", fmt.Errorf("ListTokens org_id=%s: %w", orgID, err)
	}
	return mapTokenMetadata(rows), next, nil
}

func mapTokenMetadata(rows []repository.TokenMetadata) []TokenListItem {
	out := make([]TokenListItem, 0, len(rows))
	for _, row := range rows {
		item := TokenListItem{
			ID: row.ID, Name: row.Name, Prefix: row.Prefix,
			Permissions: row.Permissions, CreatedAt: row.CreatedAt, IsRevoked: row.IsRevoked,
		}
		if row.ExpiresAt.Valid {
			t := row.ExpiresAt.Time
			item.ExpiresAt = &t
		}
		if row.RevokedAt.Valid {
			t := row.RevokedAt.Time
			item.RevokedAt = &t
		}
		out = append(out, item)
	}
	return out
}

// ErrInvalidArgument indicates a client request validation failure.
var ErrInvalidArgument = errors.New("invalid argument")
