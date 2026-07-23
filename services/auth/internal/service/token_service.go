package service

import (
	"context"
	"errors"
	"sync"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"github.com/Rick1330/ibex-harness/packages/revocation"
	"github.com/Rick1330/ibex-harness/services/auth/internal/repository"
	"github.com/Rick1330/ibex-harness/services/auth/internal/token"
	"google.golang.org/protobuf/types/known/timestamppb"
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
		return err
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
