package repository

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"time"
)

// ErrTotpSecretNotFound is returned when no TOTP row exists for the user.
var ErrTotpSecretNotFound = errors.New("totp secret not found")

// TotpSecretRow is the persistence shape for user_totp_secrets.
type TotpSecretRow struct {
	OrgID           string
	UserID          string
	Ciphertext      []byte
	WrappedDEK      []byte
	EncryptionKeyID string
	ConfirmedAt     sql.NullTime
}

// TotpSecretRepo persists sealed TOTP secrets.
type TotpSecretRepo struct {
	db *sql.DB
}

// NewTotpSecretRepo constructs a repo. db may be nil for disabled paths.
func NewTotpSecretRepo(db *sql.DB) *TotpSecretRepo {
	return &TotpSecretRepo{db: db}
}

func (r *TotpSecretRepo) withServiceAccount(ctx context.Context, fn func(*sql.Tx) error) error {
	tx, err := r.db.BeginTx(ctx, nil)
	if err != nil {
		return fmt.Errorf("totp repo: begin tx: %w", err)
	}
	defer func() { _ = tx.Rollback() }()

	if _, err := tx.ExecContext(ctx, `SELECT set_config('app.is_service_account', 'true', true)`); err != nil {
		return fmt.Errorf("totp repo: set service account: %w", err)
	}
	if err := fn(tx); err != nil {
		return err
	}
	return tx.Commit()
}

// UpsertPending inserts or replaces an unconfirmed secret.
func (r *TotpSecretRepo) UpsertPending(ctx context.Context, row TotpSecretRow) error {
	if r == nil || r.db == nil {
		return fmt.Errorf("totp repo: nil db")
	}
	return r.withServiceAccount(ctx, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(ctx, `
			INSERT INTO ibex_core.user_totp_secrets (
				org_id, user_id, ciphertext, wrapped_dek, encryption_key_id, confirmed_at
			) VALUES ($1, $2, $3, $4, $5, NULL)
			ON CONFLICT (org_id, user_id) DO UPDATE SET
				ciphertext = EXCLUDED.ciphertext,
				wrapped_dek = EXCLUDED.wrapped_dek,
				encryption_key_id = EXCLUDED.encryption_key_id,
				confirmed_at = NULL,
				updated_at = NOW()
		`, row.OrgID, row.UserID, row.Ciphertext, row.WrappedDEK, row.EncryptionKeyID)
		return err
	})
}

// Get loads a row or ErrTotpSecretNotFound.
func (r *TotpSecretRepo) Get(ctx context.Context, orgID, userID string) (TotpSecretRow, error) {
	if r == nil || r.db == nil {
		return TotpSecretRow{}, fmt.Errorf("totp repo: nil db")
	}
	var out TotpSecretRow
	err := r.withServiceAccount(ctx, func(tx *sql.Tx) error {
		return tx.QueryRowContext(ctx, `
			SELECT org_id, user_id, ciphertext, wrapped_dek, encryption_key_id, confirmed_at
			FROM ibex_core.user_totp_secrets
			WHERE org_id = $1 AND user_id = $2
		`, orgID, userID).Scan(
			&out.OrgID, &out.UserID, &out.Ciphertext, &out.WrappedDEK, &out.EncryptionKeyID, &out.ConfirmedAt,
		)
	})
	if errors.Is(err, sql.ErrNoRows) {
		return TotpSecretRow{}, ErrTotpSecretNotFound
	}
	return out, err
}

// Confirm marks enrollment confirmed.
func (r *TotpSecretRepo) Confirm(ctx context.Context, orgID, userID string, at time.Time) error {
	return r.ConfirmCiphertext(ctx, orgID, userID, nil, at)
}

// ConfirmCiphertext confirms only when ciphertext still matches the validated secret
// (compare-and-set against concurrent BeginEnrollment replacement). nil ciphertext
// falls back to org/user-only match for legacy callers.
func (r *TotpSecretRepo) ConfirmCiphertext(
	ctx context.Context, orgID, userID string, ciphertext []byte, at time.Time,
) error {
	if r == nil || r.db == nil {
		return fmt.Errorf("totp repo: nil db")
	}
	var res sql.Result
	err := r.withServiceAccount(ctx, func(tx *sql.Tx) error {
		var execErr error
		if len(ciphertext) == 0 {
			res, execErr = tx.ExecContext(ctx, `
				UPDATE ibex_core.user_totp_secrets
				SET confirmed_at = $3, updated_at = NOW()
				WHERE org_id = $1 AND user_id = $2 AND confirmed_at IS NULL
			`, orgID, userID, at)
		} else {
			res, execErr = tx.ExecContext(ctx, `
				UPDATE ibex_core.user_totp_secrets
				SET confirmed_at = $4, updated_at = NOW()
				WHERE org_id = $1 AND user_id = $2 AND confirmed_at IS NULL AND ciphertext = $3
			`, orgID, userID, ciphertext, at)
		}
		return execErr
	})
	if err != nil {
		return err
	}
	n, err := res.RowsAffected()
	if err != nil {
		return err
	}
	if n == 0 {
		return ErrTotpSecretNotFound
	}
	return nil
}
