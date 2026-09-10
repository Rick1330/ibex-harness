package repository

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"time"

	"github.com/Rick1330/ibex-harness/packages/metrics"
)

// ErrProviderCredentialNotFound is returned when no credential row exists for the org/provider.
var ErrProviderCredentialNotFound = errors.New("provider credential not found")

// ProviderCredentialRow is a sealed provider API key row.
type ProviderCredentialRow struct {
	ID              string
	OrgID           string
	ProviderName    string
	Ciphertext      []byte
	WrappedDEK      []byte
	EncryptionKeyID string
	KeyHint         string
	BaseURL         sql.NullString
	Status          string
	LastValidatedAt sql.NullTime
	CreatedAt       time.Time
	UpdatedAt       time.Time
}

// ProviderCredentialsRepository persists envelope-encrypted provider keys.
type ProviderCredentialsRepository struct {
	db  *sql.DB
	obs metrics.QueryObserver
}

// NewProviderCredentialsRepository constructs a repository. Returns ErrNilDB when db is nil.
func NewProviderCredentialsRepository(db *sql.DB, obs metrics.QueryObserver) (*ProviderCredentialsRepository, error) {
	if db == nil {
		return nil, ErrNilDB
	}
	return &ProviderCredentialsRepository{db: db, obs: obs}, nil
}

func (r *ProviderCredentialsRepository) withServiceAccount(ctx context.Context, fn func(*sql.Tx) error) error {
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

// Upsert seals a credential row for (org_id, provider_name).
func (r *ProviderCredentialsRepository) Upsert(ctx context.Context, row ProviderCredentialRow) (ProviderCredentialRow, error) {
	start := time.Now()
	defer observeQuery(r.obs, metrics.DBOpUpsertProviderCredential, start)

	var out ProviderCredentialRow
	err := r.withServiceAccount(ctx, func(tx *sql.Tx) error {
		return tx.QueryRowContext(ctx, `
			INSERT INTO ibex_core.provider_credentials (
				org_id, provider_name, ciphertext, wrapped_dek, encryption_key_id,
				key_hint, base_url, status, last_validated_at
			) VALUES (
				$1::uuid, $2, $3, $4, $5, $6, NULLIF($7, ''), $8, NOW()
			)
			ON CONFLICT (org_id, provider_name) DO UPDATE SET
				ciphertext = EXCLUDED.ciphertext,
				wrapped_dek = EXCLUDED.wrapped_dek,
				encryption_key_id = EXCLUDED.encryption_key_id,
				key_hint = EXCLUDED.key_hint,
				base_url = EXCLUDED.base_url,
				status = EXCLUDED.status,
				last_validated_at = NOW(),
				updated_at = NOW()
			RETURNING id::text, org_id::text, provider_name, ciphertext, wrapped_dek,
				encryption_key_id, key_hint, base_url, status, last_validated_at, created_at, updated_at`,
			row.OrgID, row.ProviderName, row.Ciphertext, row.WrappedDEK, row.EncryptionKeyID,
			row.KeyHint, nullStringValue(row.BaseURL), row.Status,
		).Scan(
			&out.ID, &out.OrgID, &out.ProviderName, &out.Ciphertext, &out.WrappedDEK,
			&out.EncryptionKeyID, &out.KeyHint, &out.BaseURL, &out.Status,
			&out.LastValidatedAt, &out.CreatedAt, &out.UpdatedAt,
		)
	})
	if err != nil {
		return ProviderCredentialRow{}, err
	}
	return out, nil
}

// FindByOrgProvider loads a credential by org and provider name.
func (r *ProviderCredentialsRepository) FindByOrgProvider(ctx context.Context, orgID, providerName string) (ProviderCredentialRow, error) {
	start := time.Now()
	defer observeQuery(r.obs, metrics.DBOpFindProviderCredential, start)

	var out ProviderCredentialRow
	err := r.withServiceAccount(ctx, func(tx *sql.Tx) error {
		err := tx.QueryRowContext(ctx, `
			SELECT id::text, org_id::text, provider_name, ciphertext, wrapped_dek,
				encryption_key_id, key_hint, base_url, status, last_validated_at, created_at, updated_at
			FROM ibex_core.provider_credentials
			WHERE org_id = $1::uuid AND provider_name = $2
			LIMIT 1`,
			orgID, providerName,
		).Scan(
			&out.ID, &out.OrgID, &out.ProviderName, &out.Ciphertext, &out.WrappedDEK,
			&out.EncryptionKeyID, &out.KeyHint, &out.BaseURL, &out.Status,
			&out.LastValidatedAt, &out.CreatedAt, &out.UpdatedAt,
		)
		if errors.Is(err, sql.ErrNoRows) {
			return ErrProviderCredentialNotFound
		}
		return err
	})
	if err != nil {
		return ProviderCredentialRow{}, err
	}
	return out, nil
}

// ListByOrg returns metadata rows for an organization (includes ciphertext columns for seal integrity; callers must not expose them).
func (r *ProviderCredentialsRepository) ListByOrg(ctx context.Context, orgID string) ([]ProviderCredentialRow, error) {
	start := time.Now()
	defer observeQuery(r.obs, metrics.DBOpListProviderCredentials, start)

	var rows []ProviderCredentialRow
	err := r.withServiceAccount(ctx, func(tx *sql.Tx) error {
		rs, err := tx.QueryContext(ctx, `
			SELECT id::text, org_id::text, provider_name, ciphertext, wrapped_dek,
				encryption_key_id, key_hint, base_url, status, last_validated_at, created_at, updated_at
			FROM ibex_core.provider_credentials
			WHERE org_id = $1::uuid
			ORDER BY provider_name ASC`,
			orgID,
		)
		if err != nil {
			return err
		}
		defer func() { _ = rs.Close() }()
		for rs.Next() {
			var row ProviderCredentialRow
			if err := rs.Scan(
				&row.ID, &row.OrgID, &row.ProviderName, &row.Ciphertext, &row.WrappedDEK,
				&row.EncryptionKeyID, &row.KeyHint, &row.BaseURL, &row.Status,
				&row.LastValidatedAt, &row.CreatedAt, &row.UpdatedAt,
			); err != nil {
				return err
			}
			rows = append(rows, row)
		}
		return rs.Err()
	})
	if err != nil {
		return nil, err
	}
	return rows, nil
}

// Delete removes a credential; returns ErrProviderCredentialNotFound when absent.
func (r *ProviderCredentialsRepository) Delete(ctx context.Context, orgID, providerName string) error {
	start := time.Now()
	defer observeQuery(r.obs, metrics.DBOpDeleteProviderCredential, start)

	return r.withServiceAccount(ctx, func(tx *sql.Tx) error {
		res, err := tx.ExecContext(ctx, `
			DELETE FROM ibex_core.provider_credentials
			WHERE org_id = $1::uuid AND provider_name = $2`,
			orgID, providerName,
		)
		if err != nil {
			return err
		}
		n, err := res.RowsAffected()
		if err != nil {
			return err
		}
		if n == 0 {
			return ErrProviderCredentialNotFound
		}
		return nil
	})
}

func nullStringValue(ns sql.NullString) string {
	if ns.Valid {
		return ns.String
	}
	return ""
}
