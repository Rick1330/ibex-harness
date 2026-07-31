package service

import (
	"context"
	"database/sql"
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/services/auth/internal/repository"
	"github.com/google/uuid"
)

func assertCreateTokenError(t *testing.T, err, want error) {
	t.Helper()
	if !errors.Is(err, want) {
		t.Fatalf("CreateToken err: got %v want %v", err, want)
	}
}

func assertCreateTokenOK(t *testing.T, repo *memTokenRepo, in CreateTokenInput, result CreateTokenResult) {
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
	p, ok := repo.tokens[result.TokenID]
	if !ok {
		t.Fatal("token not persisted in repo")
	}
	assertCreateTokenParams(t, in, p)
}

func assertCreateTokenParams(t *testing.T, in CreateTokenInput, p repository.CreateTokenParams) {
	t.Helper()
	if p.Description != in.Description {
		t.Fatalf("description=%q want %q", p.Description, in.Description)
	}
	if p.Permissions != in.Permissions {
		t.Fatalf("permissions=%d want %d", p.Permissions, in.Permissions)
	}
	if !sameOptionalString(p.UserID, in.UserID) {
		t.Fatalf("user_id=%v want %v", p.UserID, in.UserID)
	}
	if !sameOptionalString(p.AgentID, in.AgentID) {
		t.Fatalf("agent_id=%v want %v", p.AgentID, in.AgentID)
	}
	if !sameOptionalTime(p.ExpiresAt, in.ExpiresAt) {
		t.Fatalf("expires_at=%v want %v", p.ExpiresAt, in.ExpiresAt)
	}
}

func sameOptionalString(got, want *string) bool {
	if got == nil || want == nil {
		return got == nil && want == nil
	}
	return *got == *want
}

func sameOptionalTime(got, want *time.Time) bool {
	if got == nil || want == nil {
		return got == nil && want == nil
	}
	return got.Equal(*want)
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
	assertCreateTokenOK(t, repo, tc.in, result)
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
		OrgID: uuid.NewString(), Name: "x", TokenType: TokenTypePAT,
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
	assertTokenListItem(t, rows[0], "t1", 1, false, &expires, nil)
	assertTokenListItem(t, rows[1], "t2", 2, true, nil, &revokedAt)
}

func assertTokenListItem(t *testing.T, got TokenListItem, id string, perms int64, revoked bool, expires, revokedAt *time.Time) {
	t.Helper()
	if got.ID != id {
		t.Fatalf("id=%q want %q", got.ID, id)
	}
	if got.Permissions != perms {
		t.Fatalf("permissions=%d want %d", got.Permissions, perms)
	}
	if got.IsRevoked != revoked {
		t.Fatalf("is_revoked=%v want %v", got.IsRevoked, revoked)
	}
	if !sameOptionalTime(got.ExpiresAt, expires) {
		t.Fatalf("expires_at=%v want %v", got.ExpiresAt, expires)
	}
	if !sameOptionalTime(got.RevokedAt, revokedAt) {
		t.Fatalf("revoked_at=%v want %v", got.RevokedAt, revokedAt)
	}
}

func TestTokenService_ListTokens_RepoErrorWrapped(t *testing.T) {
	t.Parallel()
	orgID := uuid.New().String()
	_, _, err := testTokenService(errTokenRepo{}).ListTokens(context.Background(), orgID, "", 10)
	if err == nil {
		t.Fatal("expected error")
	}
	msg := err.Error()
	if !strings.Contains(msg, "ListTokens org_id="+orgID) {
		t.Fatalf("err=%q want ListTokens org_id wrap", msg)
	}
	if !strings.Contains(msg, "db down") {
		t.Fatalf("err=%q want wrapped repo cause", msg)
	}
}
