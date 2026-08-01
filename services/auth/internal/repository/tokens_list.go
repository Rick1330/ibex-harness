package repository

import (
	"context"
	"database/sql"
	"fmt"
	"strings"
	"time"

	"github.com/Rick1330/ibex-harness/packages/metrics"
)

// ListTokens returns token metadata for an org with cursor pagination.
func (r *TokensRepository) ListTokens(ctx context.Context, orgID, cursor string, limit int) ([]TokenMetadata, string, error) {
	start := time.Now()
	defer observeQuery(r.obs, metrics.DBOpListTokens, start)

	limit = normalizeTokenListLimit(limit)
	cursorTS, cursorID, err := decodeTokenCursor(cursor)
	if err != nil {
		return nil, "", fmt.Errorf("ListTokens cursor: %w", err)
	}
	rows, err := r.queryTokenMetadataPage(ctx, listTokensQuery{
		orgID: orgID, cursor: cursor, cursorTS: cursorTS, cursorID: cursorID, limit: limit,
	})
	if err != nil {
		return nil, "", err
	}
	return paginateTokenMetadata(rows, limit)
}

func normalizeTokenListLimit(limit int) int {
	if limit <= 0 || limit > 100 {
		return 50
	}
	return limit
}

type listTokensQuery struct {
	orgID    string
	cursor   string
	cursorTS time.Time
	cursorID string
	limit    int
}

func (r *TokensRepository) queryTokenMetadataPage(ctx context.Context, q listTokensQuery) ([]TokenMetadata, error) {
	var rows []TokenMetadata
	err := r.withServiceAccount(ctx, func(tx *sql.Tx) error {
		sqlText, args := buildListTokensSQL(q)
		result, err := tx.QueryContext(ctx, sqlText, args...)
		if err != nil {
			return err
		}
		defer func() { _ = result.Close() }()
		return scanTokenMetadataRows(result, &rows)
	})
	return rows, err
}

func buildListTokensSQL(q listTokensQuery) (string, []any) {
	query := `
			SELECT id::text, name, prefix, permissions, expires_at, created_at, revoked_at, is_revoked
			FROM ibex_core.tokens
			WHERE org_id = $1::uuid`
	args := []any{q.orgID}
	argN := 2
	if q.cursor != "" {
		query += fmt.Sprintf(` AND (created_at < $%d OR (created_at = $%d AND id < $%d::uuid))`, argN, argN, argN+1)
		args = append(args, q.cursorTS, q.cursorID)
		argN += 2
	}
	query += fmt.Sprintf(` ORDER BY created_at DESC, id DESC LIMIT $%d`, argN)
	args = append(args, q.limit+1)
	return query, args
}

func scanTokenMetadataRows(result *sql.Rows, rows *[]TokenMetadata) error {
	for result.Next() {
		var m TokenMetadata
		if err := result.Scan(
			&m.ID, &m.Name, &m.Prefix, &m.Permissions, &m.ExpiresAt, &m.CreatedAt, &m.RevokedAt, &m.IsRevoked,
		); err != nil {
			return err
		}
		*rows = append(*rows, m)
	}
	return result.Err()
}

func paginateTokenMetadata(rows []TokenMetadata, limit int) ([]TokenMetadata, string, error) {
	var next string
	if len(rows) > limit {
		last := rows[limit-1]
		next = encodeTokenCursor(last.CreatedAt, last.ID)
		rows = rows[:limit]
	}
	return rows, next, nil
}

func encodeTokenCursor(createdAt time.Time, id string) string {
	return fmt.Sprintf("%d|%s", createdAt.UTC().UnixNano(), id)
}

func decodeTokenCursor(cursor string) (time.Time, string, error) {
	if cursor == "" {
		return time.Time{}, "", nil
	}
	nano, id, err := parseTokenCursorParts(cursor)
	if err != nil {
		return time.Time{}, "", err
	}
	return time.Unix(0, nano).UTC(), id, nil
}

func parseTokenCursorParts(cursor string) (nano int64, id string, err error) {
	parts := strings.SplitN(cursor, "|", 2)
	if len(parts) != 2 {
		return 0, "", fmt.Errorf("invalid cursor %q", cursor)
	}
	if parts[0] == "" || parts[1] == "" {
		return 0, "", fmt.Errorf("invalid cursor %q", cursor)
	}
	if _, err := fmt.Sscanf(parts[0], "%d", &nano); err != nil {
		return 0, "", fmt.Errorf("invalid cursor timestamp: %w", err)
	}
	return nano, parts[1], nil
}
