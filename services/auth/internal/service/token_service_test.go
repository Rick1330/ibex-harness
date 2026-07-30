package service

import (
	"context"
	"database/sql"
	"errors"
	"testing"
	"time"

	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"github.com/Rick1330/ibex-harness/services/auth/internal/repository"
	"github.com/google/uuid"
)

func assertCreateTokenError(t *testing.T, err, want error) {
	t.Helper()
	if !errors.Is(err, want) {
		t.Fatalf("CreateToken err: got %v want %v", err, want)
	}
}

func assertCreateTokenOK(t *testing.T, repo *memTokenRepo, result CreateTokenResult) {
	t.Helper()
	if result.TokenID == "" {
		t.Fatalf("incomplete result: %+v", result)
	}
	if result.Plaintext == "" {
		t.Fatalf("incomplete result: %+v", result)
	}
	if result.Prefix == "" {
		t.Fatalf("incomplete result: %+v", result)
	}
	if _, ok := repo.tokens[result.TokenID]; !ok {
		t.Fatal("token not persisted in repo")
	}
}

func runCreateTokenCase(t *testing.T, tc createTokenCase) {
	t.Helper()
	repo := newMemTokenRepo()
	result, err := testTokenService(repo).CreateToken(context.Background(), tc.in)
	if tc.wantErr != nil {
		assertCreateTokenError(t, err, tc.wantErr)
		return
	}
	if err != nil {
		t.Fatalf("CreateToken: %v", err)
	}
	assertCreateTokenOK(t, repo, result)
}

func TestTokenService_CreateToken(t *testing.T) {
	t.Parallel()
	orgID := uuid.New().String()
	expires := time.Now().UTC().Add(24 * time.Hour)
	for _, tc := range createTokenCases(orgID, uuid.NewString(), uuid.NewString(), expires) {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			runCreateTokenCase(t, tc)
		})
	}
}

func TestTokenService_CreateToken_repoError(t *testing.T) {
	t.Parallel()
	svc := testTokenService(errTokenRepo{})
	_, err := svc.CreateToken(context.Background(), CreateTokenInput{
		OrgID: uuid.NewString(), Name: "x", TokenType: authv1.TokenType_TOKEN_TYPE_PAT,
	})
	if err == nil {
		t.Fatal("expected error")
	}
}

func TestTokenService_RevokeToken(t *testing.T) {
	t.Parallel()
	orgID := uuid.New().String()
	tokenID := uuid.New().String()
	repo := newMemTokenRepo()
	repo.tokens[tokenID] = repository.CreateTokenParams{ID: tokenID, OrgID: orgID}
	svc := testTokenService(repo)
	if err := svc.RevokeToken(context.Background(), RevokeTokenParams{
		OrgID: orgID, TokenID: tokenID,
	}); err != nil {
		t.Fatalf("RevokeToken: %v", err)
	}
	if !repo.revoked[tokenID] {
		t.Fatal("token not marked revoked")
	}
	err := svc.RevokeToken(context.Background(), RevokeTokenParams{
		OrgID: orgID, TokenID: uuid.NewString(),
	})
	if !errors.Is(err, ErrTokenNotFound) {
		t.Fatalf("expected ErrTokenNotFound, got %v", err)
	}
}

func TestTokenService_ListTokens(t *testing.T) {
	t.Parallel()
	orgID := uuid.New().String()
	expires := time.Now().UTC().Add(time.Hour)
	revokedAt := time.Now().UTC().Add(-time.Minute)
	repo := newMemTokenRepo()
	repo.list = []repository.TokenMetadata{
		{
			ID: "t1", Name: "a", Prefix: "ibex_pat_a", Permissions: 1,
			CreatedAt: time.Now().UTC(),
			ExpiresAt: sql.NullTime{Time: expires, Valid: true},
		},
		{
			ID: "t2", Name: "b", Prefix: "ibex_pat_b", Permissions: 2,
			CreatedAt: time.Now().UTC(), IsRevoked: true,
			RevokedAt: sql.NullTime{Time: revokedAt, Valid: true},
		},
	}
	rows, next, err := testTokenService(repo).ListTokens(context.Background(), orgID, "", 10)
	if err != nil {
		t.Fatalf("ListTokens: %v", err)
	}
	if len(rows) != 2 || next != "" {
		t.Fatalf("list: len=%d next=%q", len(rows), next)
	}
}
