package repository

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"time"
)

// ErrNotFound is returned when a token row does not exist for the given org scope.
var ErrNotFound = errors.New("token not found")

// TokenRow is a token record used for validation.
type TokenRow struct {
	ID          string
	OrgID       string
	UserID      sql.NullString
	AgentID     sql.NullString
	Permissions int64
	ExpiresAt   sql.NullTime
	Hash        string
}

// TokensRepository loads tokens under the service-account RLS context.
type TokensRepository struct {
	db *sql.DB
}

func NewTokensRepository(db *sql.DB) *TokensRepository {
	return &TokensRepository{db: db}
}

// FindActiveByPrefix returns a non-revoked, non-expired token with the given prefix.
func (r *TokensRepository) FindActiveByPrefix(ctx context.Context, prefix string) (TokenRow, error) {
	var row TokenRow
	err := r.withServiceAccount(ctx, func(tx *sql.Tx) error {
		return tx.QueryRowContext(ctx, `
			SELECT id::text, org_id::text, user_id::text, agent_id::text, permissions, expires_at, hash
			FROM ibex_core.tokens
			WHERE prefix = $1
			  AND is_revoked = false
			  AND (expires_at IS NULL OR expires_at > NOW())
			LIMIT 1`,
			prefix,
		).Scan(&row.ID, &row.OrgID, &row.UserID, &row.AgentID, &row.Permissions, &row.ExpiresAt, &row.Hash)
	})
	if err != nil {
		return TokenRow{}, err
	}
	return row, nil
}

func (r *TokensRepository) withServiceAccount(ctx context.Context, fn func(*sql.Tx) error) error {
	tx, err := r.db.BeginTx(ctx, nil)
	if err != nil {
		return fmt.Errorf("begin tx: %w", err)
	}
	defer func() { _ = tx.Rollback() }()

	if _, err := tx.ExecContext(ctx, `SELECT set_config('app.is_service_account', 'true', true)`); err != nil {
		return fmt.Errorf("set service account: %w", err)
	}
	if err := fn(tx); err != nil {
		return err
	}
	return tx.Commit()
}

// InsertTestToken inserts a token row (integration tests only).
func (r *TokensRepository) InsertTestToken(ctx context.Context, orgID, prefix, hash, name string, permissions int64, revoked bool, expiresAt *time.Time) (string, error) {
	var id string
	err := r.withServiceAccount(ctx, func(tx *sql.Tx) error {
		var exp any
		if expiresAt != nil {
			exp = *expiresAt
		}
		return tx.QueryRowContext(ctx, `
			INSERT INTO ibex_core.tokens (org_id, type, hash, prefix, name, permissions, is_revoked, expires_at)
			VALUES ($1::uuid, 'pat', $2, $3, $4, $5, $6, $7)
			RETURNING id::text`,
			orgID, hash, prefix, name, permissions, revoked, exp,
		).Scan(&id)
	})
	return id, err
}

// CreateTokenParams holds persisted token fields (never plaintext).
type CreateTokenParams struct {
	ID          string
	OrgID       string
	Name        string
	Description string
	Hash        string
	Prefix      string
	Permissions int64
	UserID      *string
	AgentID     *string
	ExpiresAt   *time.Time
}

// TokenMetadata is a safe token row view without hash.
type TokenMetadata struct {
	ID          string
	Name        string
	Prefix      string
	Permissions int64
	ExpiresAt   sql.NullTime
	CreatedAt   time.Time
	RevokedAt   sql.NullTime
	IsRevoked   bool
}

// CreateToken inserts a new PAT row and returns its id.
func (r *TokensRepository) CreateToken(ctx context.Context, p CreateTokenParams) (string, error) {
	var id string
	err := r.withServiceAccount(ctx, func(tx *sql.Tx) error {
		var exp any
		if p.ExpiresAt != nil {
			exp = *p.ExpiresAt
		}
		var userID, agentID any
		if p.UserID != nil {
			userID = *p.UserID
		}
		if p.AgentID != nil {
			agentID = *p.AgentID
		}
		return tx.QueryRowContext(ctx, `
			INSERT INTO ibex_core.tokens (
				id, org_id, user_id, agent_id, type, hash, prefix, name, description,
				permissions, expires_at
			)
			VALUES ($1::uuid, $2::uuid, $3::uuid, $4::uuid, 'pat', $5, $6, $7, $8, $9, $10)
			RETURNING id::text`,
			p.ID, p.OrgID, userID, agentID, p.Hash, p.Prefix, p.Name, p.Description, p.Permissions, exp,
		).Scan(&id)
	})
	return id, err
}

// RevokeToken marks a token revoked within org scope.
func (r *TokensRepository) RevokeToken(ctx context.Context, orgID, tokenID, revokedBy string, reason *string) error {
	return r.withServiceAccount(ctx, func(tx *sql.Tx) error {
		var revokedByArg any
		if revokedBy != "" {
			revokedByArg = revokedBy
		}
		res, err := tx.ExecContext(ctx, `
			UPDATE ibex_core.tokens
			SET is_revoked = true,
			    revoked_at = NOW(),
			    revoked_by = $3::uuid,
			    revoke_reason = $4
			WHERE id = $1::uuid AND org_id = $2::uuid AND is_revoked = false`,
			tokenID, orgID, revokedByArg, reason,
		)
		if err != nil {
			return err
		}
		n, err := res.RowsAffected()
		if err != nil {
			return err
		}
		if n == 0 {
			return ErrNotFound
		}
		return nil
	})
}

// ListTokens returns token metadata for an org with cursor pagination.
func (r *TokensRepository) ListTokens(ctx context.Context, orgID, cursor string, limit int) ([]TokenMetadata, string, error) {
	if limit <= 0 || limit > 100 {
		limit = 50
	}
	var rows []TokenMetadata
	err := r.withServiceAccount(ctx, func(tx *sql.Tx) error {
		query := `
			SELECT id::text, name, prefix, permissions, expires_at, created_at, revoked_at, is_revoked
			FROM ibex_core.tokens
			WHERE org_id = $1::uuid`
		args := []any{orgID}
		argN := 2
		if cursor != "" {
			query += fmt.Sprintf(` AND id::text < $%d`, argN)
			args = append(args, cursor)
			argN++
		}
		query += fmt.Sprintf(` ORDER BY created_at DESC, id DESC LIMIT $%d`, argN)
		args = append(args, limit+1)

		result, err := tx.QueryContext(ctx, query, args...)
		if err != nil {
			return err
		}
		defer func() { _ = result.Close() }()
		for result.Next() {
			var m TokenMetadata
			if err := result.Scan(
				&m.ID, &m.Name, &m.Prefix, &m.Permissions, &m.ExpiresAt, &m.CreatedAt, &m.RevokedAt, &m.IsRevoked,
			); err != nil {
				return err
			}
			rows = append(rows, m)
		}
		return result.Err()
	})
	if err != nil {
		return nil, "", err
	}
	var next string
	if len(rows) > limit {
		next = rows[limit-1].ID
		rows = rows[:limit]
	}
	return rows, next, nil
}

// InsertTestOrganization inserts an organization (integration tests only).
func (r *TokensRepository) InsertTestOrganization(ctx context.Context, name, slug string) (string, error) {
	var id string
	err := r.withServiceAccount(ctx, func(tx *sql.Tx) error {
		return tx.QueryRowContext(ctx, `
			INSERT INTO ibex_core.organizations (name, slug)
			VALUES ($1, $2)
			RETURNING id::text`, name, slug,
		).Scan(&id)
	})
	return id, err
}
