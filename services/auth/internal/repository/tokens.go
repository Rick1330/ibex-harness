package repository

import (
	"context"
	"database/sql"
	"errors"
	"time"

	"github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/google/uuid"
)

// ErrNotFound is returned when a token row does not exist for the given org scope.
var ErrNotFound = errors.New("token not found")

// TokenRow is a token record used for validation.
type TokenRow struct {
	ID          string
	OrgID       string
	OrgStatus   string
	UserID      sql.NullString
	AgentID     sql.NullString
	Permissions int64
	ExpiresAt   sql.NullTime
	Hash        string
}

// TokensRepository loads tokens. Tenant-scoped writes and lists run under the
// ibex_app role with app.current_org_id pinned; the cross-tenant validation
// lookup uses the SECURITY DEFINER reader instead of a session flag.
type TokensRepository struct {
	db  *sql.DB
	obs metrics.QueryObserver
}

// findActiveTokenByPrefixSQL is the SECURITY DEFINER reader. Its eight output
// columns match the Scan order below; the owner is ibex_service and EXECUTE is
// granted to ibex_runtime only, so it is callable under both the current owner
// login and a future runtime DSN without a role pin.
const findActiveTokenByPrefixSQL = `SELECT * FROM ibex_core.auth_find_token_by_prefix($1)`

// FindActiveByPrefix returns a non-revoked, non-expired token with the given
// prefix. A miss returns sql.ErrNoRows so the Validator can equalize Argon2
// cost before denying.
func (r *TokensRepository) FindActiveByPrefix(ctx context.Context, prefix string) (TokenRow, error) {
	start := time.Now()
	defer observeQuery(r.obs, metrics.DBOpFindTokenByPrefix, start)

	var row TokenRow
	err := withReaderTx(ctx, r.db, func(tx *sql.Tx) error {
		return tx.QueryRowContext(ctx, findActiveTokenByPrefixSQL, prefix).Scan(
			&row.ID, &row.OrgID, &row.OrgStatus, &row.UserID, &row.AgentID, &row.Permissions, &row.ExpiresAt, &row.Hash,
		)
	})
	if err != nil {
		return TokenRow{}, err
	}
	return row, nil
}

// TestTokenParams is one seeded token row (integration tests only).
type TestTokenParams struct {
	OrgID       string
	Prefix      string
	Hash        string
	Name        string
	Permissions int64
	Revoked     bool
	ExpiresAt   *time.Time
}

// InsertTestToken inserts a token row (integration tests only).
func (r *TokensRepository) InsertTestToken(ctx context.Context, p TestTokenParams) (string, error) {
	var id string
	err := withTenant(ctx, r.db, p.OrgID, func(tx *sql.Tx) error {
		var exp any
		if p.ExpiresAt != nil {
			exp = *p.ExpiresAt
		}
		return tx.QueryRowContext(ctx, `
			INSERT INTO ibex_core.tokens (org_id, type, hash, prefix, name, permissions, is_revoked, expires_at)
			VALUES ($1::uuid, 'pat', $2, $3, $4, $5, $6, $7)
			RETURNING id::text`,
			p.OrgID, p.Hash, p.Prefix, p.Name, p.Permissions, p.Revoked, exp,
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
	start := time.Now()
	defer observeQuery(r.obs, metrics.DBOpCreateToken, start)

	var id string
	err := withTenant(ctx, r.db, p.OrgID, func(tx *sql.Tx) error {
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

// RevokeTokenInput scopes a revoke operation to one org token.
type RevokeTokenInput struct {
	OrgID     string
	TokenID   string
	RevokedBy string
	Reason    *string
}

// RevokeToken marks a token revoked within org scope.
func (r *TokensRepository) RevokeToken(ctx context.Context, in RevokeTokenInput) error {
	start := time.Now()
	defer observeQuery(r.obs, "revoke_token", start)

	return withTenant(ctx, r.db, in.OrgID, func(tx *sql.Tx) error {
		var revokedByArg any
		if in.RevokedBy != "" {
			revokedByArg = in.RevokedBy
		}
		res, err := tx.ExecContext(ctx, `
			UPDATE ibex_core.tokens
			SET is_revoked = true,
			    revoked_at = NOW(),
			    revoked_by = $3::uuid,
			    revoke_reason = $4
			WHERE id = $1::uuid AND org_id = $2::uuid AND is_revoked = false`,
			in.TokenID, in.OrgID, revokedByArg, in.Reason,
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

// OrgUserRef scopes token listing to one org member.
type OrgUserRef struct {
	OrgID  string
	UserID string
}

// ListActiveTokenIDsByUser returns non-revoked token IDs for a user within an org.
func (r *TokensRepository) ListActiveTokenIDsByUser(ctx context.Context, scope OrgUserRef) ([]string, error) {
	start := time.Now()
	defer observeQuery(r.obs, "list_active_token_ids_by_user", start)

	var ids []string
	err := withTenant(ctx, r.db, scope.OrgID, func(tx *sql.Tx) error {
		rows, err := tx.QueryContext(ctx, `
			SELECT id::text
			FROM ibex_core.tokens
			WHERE org_id = $1::uuid
			  AND user_id = $2::uuid
			  AND is_revoked = false
			ORDER BY created_at ASC, id ASC`,
			scope.OrgID, scope.UserID,
		)
		if err != nil {
			return err
		}
		defer func() { _ = rows.Close() }()
		for rows.Next() {
			var id string
			if err := rows.Scan(&id); err != nil {
				return err
			}
			ids = append(ids, id)
		}
		return rows.Err()
	})
	return ids, err
}

// InsertTestOrganization inserts an organization (integration tests only). The
// id is generated here so the insert can run with the tenant selector pinned to
// the row it is about to create.
func (r *TokensRepository) InsertTestOrganization(ctx context.Context, name, slug string) (string, error) {
	id := uuid.NewString()
	err := withTenant(ctx, r.db, id, func(tx *sql.Tx) error {
		return tx.QueryRowContext(ctx, `
			INSERT INTO ibex_core.organizations (id, name, slug)
			VALUES ($1::uuid, $2, $3)
			RETURNING id::text`, id, name, slug,
		).Scan(&id)
	})
	return id, err
}
