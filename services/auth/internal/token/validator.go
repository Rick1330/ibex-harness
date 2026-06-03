package token

import (
	"context"
	"database/sql"
	"errors"
	"time"

	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"github.com/Rick1330/ibex-harness/services/auth/internal/repository"
	"google.golang.org/protobuf/types/known/timestamppb"
)

// Validator validates bearer tokens against Postgres.
type Validator struct {
	repo   *repository.TokensRepository
	argon2 Argon2Params
}

func NewValidator(repo *repository.TokensRepository, argon2 Argon2Params) *Validator {
	return &Validator{repo: repo, argon2: argon2}
}

// Validate returns a proto response or ErrUnauthenticated.
func (v *Validator) Validate(ctx context.Context, accessToken string) (*authv1.ValidateTokenResponse, error) {
	parsed, err := ParsePAT(accessToken)
	if err != nil {
		return nil, ErrUnauthenticated
	}

	row, err := v.repo.FindActiveByPrefix(ctx, parsed.Prefix)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return nil, ErrUnauthenticated
		}
		return nil, err
	}

	ok, err := VerifyBearer(row.Hash, parsed.Bearer, v.argon2)
	if err != nil || !ok {
		return nil, ErrUnauthenticated
	}

	resp := &authv1.ValidateTokenResponse{
		OrgId:       row.OrgID,
		Permissions: row.Permissions,
		TokenId:     &row.ID,
	}
	if row.AgentID.Valid {
		resp.AgentId = &row.AgentID.String
	}
	if row.UserID.Valid {
		resp.UserId = &row.UserID.String
	}
	if row.ExpiresAt.Valid {
		ts := timestamppb.New(row.ExpiresAt.Time.UTC())
		resp.ExpiresAt = ts
	}
	return resp, nil
}

// HashForTest exposes HashBearer for integration tests in the auth module.
func HashForTest(bearer string, p Argon2Params) (string, error) {
	return HashBearer(bearer, p)
}

// MustParsePATForTest parses PAT or panics in tests.
func MustParsePATForTest(accessToken string) ParsedPAT {
	p, err := ParsePAT(accessToken)
	if err != nil {
		panic(err)
	}
	return p
}

// FutureExpiry returns a time suitable for non-expiring test tokens with optional expiry field.
func FutureExpiry() *time.Time {
	t := time.Now().UTC().Add(24 * time.Hour)
	return &t
}
