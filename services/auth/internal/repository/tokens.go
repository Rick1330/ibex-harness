package repository

import (
	"context"
	"database/sql"
	"fmt"
	"time"
)

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
