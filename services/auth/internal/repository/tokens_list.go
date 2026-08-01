package repository

import (
	"context"
	"database/sql"
	"fmt"
	"strings"
	"time"

	"github.com/Rick1330/ibex-harness/packages/metrics"
)

// Fixed SQL shapes — placeholders only; never interpolate user values into the text.
const listTokensSQL = `
			SELECT id::text, name, prefix, permissions, expires_at, created_at, revoked_at, is_revoked
			FROM ibex_core.tokens
			WHERE org_id = $1::uuid
			ORDER BY created_at DESC, id DESC LIMIT $2`

const listTokensSQLWithCursor = `
			SELECT id::text, name, prefix, permissions, expires_at, created_at, revoked_at, is_revoked
			FROM ibex_core.tokens
			WHERE org_id = $1::uuid
			  AND (created_at < $2 OR (created_at = $2 AND id < $3::uuid))
			ORDER BY created_at DESC, id DESC LIMIT $4`

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
		result, err := queryListTokens(ctx, tx, q)
		if err != nil {
			return err
		}
		defer func() { _ = result.Close() }()
		return scanTokenMetadataRows(result, &rows)
	})
	return rows, err
}

func queryListTokens(ctx context.Context, tx *sql.Tx, q listTokensQuery) (*sql.Rows, error) {
	if q.cursor == "" {
		return tx.QueryContext(ctx, listTokensSQL, q.orgID, q.limit+1)
	}
	return tx.QueryContext(ctx, listTokensSQLWithCursor, q.orgID, q.cursorTS, q.cursorID, q.limit+1)
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
