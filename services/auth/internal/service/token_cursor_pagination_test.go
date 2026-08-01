package service

import (
	"context"
	"fmt"
	"sort"
	"strings"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/services/auth/internal/repository"
	"github.com/Rick1330/ibex-harness/services/auth/internal/token"
	"github.com/google/uuid"
)

func sortTokenRows(rows []repository.TokenMetadata) {
	sort.Slice(rows, func(i, j int) bool {
		if rows[i].CreatedAt.Equal(rows[j].CreatedAt) {
			return rows[i].ID > rows[j].ID
		}
		return rows[i].CreatedAt.After(rows[j].CreatedAt)
	})
}

func tokenRowBeforeCursor(row repository.TokenMetadata, cursorTS time.Time, cursorID string) bool {
	if row.CreatedAt.Before(cursorTS) {
		return true
	}
	return row.CreatedAt.Equal(cursorTS) && row.ID < cursorID
}

func filterTokensAfterCursor(rows []repository.TokenMetadata, cursor string) ([]repository.TokenMetadata, error) {
	if cursor == "" {
		return rows, nil
	}
	cursorTS, cursorID, err := decodeMemTokenCursor(cursor)
	if err != nil {
		return nil, err
	}
	filtered := rows[:0]
	for _, row := range rows {
		if tokenRowBeforeCursor(row, cursorTS, cursorID) {
			filtered = append(filtered, row)
		}
	}
	return filtered, nil
}

func paginateTokenRows(rows []repository.TokenMetadata, limit int) ([]repository.TokenMetadata, string) {
	if limit <= 0 {
		limit = 50
	}
	if len(rows) <= limit {
		return rows, ""
	}
	last := rows[limit-1]
	return rows[:limit], encodeMemTokenCursor(last.CreatedAt, last.ID)
}

func encodeMemTokenCursor(createdAt time.Time, id string) string {
	return fmt.Sprintf("%d|%s", createdAt.UTC().UnixNano(), id)
}

func decodeMemTokenCursor(cursor string) (time.Time, string, error) {
	parts := strings.SplitN(cursor, "|", 2)
	if len(parts) != 2 {
		return time.Time{}, "", fmt.Errorf("invalid cursor %q", cursor)
	}
	var nano int64
	if _, err := fmt.Sscanf(parts[0], "%d", &nano); err != nil {
		return time.Time{}, "", err
	}
	return time.Unix(0, nano).UTC(), parts[1], nil
}

func testTokenService(repo tokenRepo) *TokenService {
	return NewTokenService(repo, token.DefaultArgon2Params(), logger.Discard("auth"), nil).
		WithSubjectLookup(allowAllSubjects{})
}

type allowAllSubjects struct{}

func (allowAllSubjects) AgentBelongsToOrg(context.Context, uuid.UUID, uuid.UUID) (bool, error) {
	return true, nil
}

func (allowAllSubjects) UserBelongsToOrg(context.Context, uuid.UUID, uuid.UUID) (bool, error) {
	return true, nil
}

type errTokenRepo struct{}

func (errTokenRepo) CreateToken(context.Context, repository.CreateTokenParams) (string, error) {
	return "", fmt.Errorf("db down")
}

func (errTokenRepo) RevokeToken(context.Context, repository.RevokeTokenInput) error {
	return fmt.Errorf("db down")
}

func (errTokenRepo) ListTokens(context.Context, string, string, int) ([]repository.TokenMetadata, string, error) {
	return nil, "", fmt.Errorf("db down")
}

func TestDecodeMemTokenCursor_invalid(t *testing.T) {
	t.Parallel()
	if _, _, err := decodeMemTokenCursor("bad"); err == nil {
		t.Fatal("expected error")
	}
}
