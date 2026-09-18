package billing

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"time"

	"github.com/google/uuid"
)

// Store loads budget periods and published rate cards from Postgres (service role).
type Store struct {
	db *sql.DB
}

// NewStore constructs a Store. db must be non-nil.
func NewStore(db *sql.DB) (*Store, error) {
	if db == nil {
		return nil, fmt.Errorf("billing: db is required")
	}
	return &Store{db: db}, nil
}

// LoadOrg returns the active hard_cap period (if any) plus the latest published card.
func (s *Store) LoadOrg(ctx context.Context, orgID uuid.UUID) (BudgetSnapshot, error) {
	if orgID == uuid.Nil {
		return BudgetSnapshot{}, fmt.Errorf("billing: org_id is required")
	}
	tx, err := s.db.BeginTx(ctx, &sql.TxOptions{ReadOnly: true})
	if err != nil {
		return BudgetSnapshot{}, err
	}
	defer func() { _ = tx.Rollback() }()

	if _, err := tx.ExecContext(ctx, `SELECT set_config('app.is_service_account', 'true', true)`); err != nil {
		return BudgetSnapshot{}, fmt.Errorf("billing: set service account: %w", err)
	}

	snap := BudgetSnapshot{}
	now := time.Now().UTC()
	row := tx.QueryRowContext(ctx, `
		SELECT id, cap_cents, spent_cents_cached, enforcement_mode, period_start, period_end
		FROM ibex_billing.budget_periods
		WHERE org_id = $1::uuid
		  AND period_start <= $2
		  AND period_end > $2
		  AND enforcement_mode = 'hard_cap'
		ORDER BY period_start DESC
		LIMIT 1`, orgID, now)
	var mode string
	err = row.Scan(&snap.PeriodID, &snap.CapCents, &snap.SpentCents, &mode, &snap.PeriodStart, &snap.PeriodEnd)
	switch {
	case err == sql.ErrNoRows:
		// No active hard_cap period: allow (no spend gate configured).
	case err != nil:
		return BudgetSnapshot{}, fmt.Errorf("billing: load budget: %w", err)
	default:
		snap.EnforcementMode = EnforcementMode(mode)
		snap.HasHardCap = true
	}

	card, err := loadPublishedCard(ctx, tx, orgID)
	if err != nil {
		return BudgetSnapshot{}, err
	}
	snap.PublishedCard = card
	if err := tx.Commit(); err != nil {
		return BudgetSnapshot{}, err
	}
	return snap, nil
}

func loadPublishedCard(ctx context.Context, tx *sql.Tx, orgID uuid.UUID) (CardVersion, error) {
	var version int64
	var pricesJSON []byte
	err := tx.QueryRowContext(ctx, `
		SELECT v.version, v.prices
		FROM ibex_billing.rate_card_versions v
		JOIN ibex_billing.rate_cards c ON c.id = v.rate_card_id
		WHERE c.org_id = $1::uuid AND c.status = 'published'
		ORDER BY v.version DESC
		LIMIT 1`, orgID).Scan(&version, &pricesJSON)
	if err == sql.ErrNoRows {
		return CardVersion{}, nil
	}
	if err != nil {
		return CardVersion{}, fmt.Errorf("billing: load rate card: %w", err)
	}
	var prices []PriceRow
	if len(pricesJSON) > 0 {
		if err := json.Unmarshal(pricesJSON, &prices); err != nil {
			return CardVersion{}, fmt.Errorf("billing: decode prices: %w", err)
		}
	}
	return CardVersion{Version: fmt.Sprintf("%d", version), Prices: prices}, nil
}
