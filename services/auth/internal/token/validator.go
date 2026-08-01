package token

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"time"

	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"google.golang.org/protobuf/types/known/timestamppb"
)

// tokenLookup loads active token rows for validation.
type tokenLookup interface {
	FindActiveByPrefix(ctx context.Context, prefix string) (Row, error)
}

// Validator validates bearer tokens against Postgres.
type Validator struct {
	repo   tokenLookup
	argon2 Argon2Params
}

func NewValidator(repo tokenLookup, argon2 Argon2Params) *Validator {
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
		return nil, fmt.Errorf("Validator.Validate prefix=%s: %w", parsed.Prefix, err)
	}

	ok, err := VerifyBearer(row.Hash, parsed.Bearer, v.argon2)
	if err != nil || !ok {
		return nil, ErrUnauthenticated
	}

	return validateResponseFromRow(row), nil
}

func validateResponseFromRow(row Row) *authv1.ValidateTokenResponse {
	resp := &authv1.ValidateTokenResponse{
		OrgId:       row.OrgID,
		Permissions: row.Permissions,
		TokenId:     &row.ID,
	}
	if row.AgentID != nil {
		resp.AgentId = row.AgentID
	}
	if row.UserID != nil {
		resp.UserId = row.UserID
	}
	if row.ExpiresAt != nil {
		resp.ExpiresAt = timestamppb.New(row.ExpiresAt.UTC())
	}
	return resp
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
