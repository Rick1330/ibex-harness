package billing

import (
	"context"
	"time"

	"github.com/google/uuid"
)

// BudgetSnapshot is the loader result for one org's active spend-cap window.
type BudgetSnapshot struct {
	PeriodID        uuid.UUID
	CapCents        int64
	SpentCents      int64
	EnforcementMode EnforcementMode
	PeriodStart     time.Time
	PeriodEnd       time.Time
	// HasHardCap is true when an active hard_cap period exists.
	HasHardCap bool
	// PublishedCard is the org's current published rate card (most recently
	// updated published card, then that card's latest version).
	PublishedCard CardVersion
}

// RemainingCents returns cap - spent, floored at 0.
func (s BudgetSnapshot) RemainingCents() int64 {
	rem := s.CapCents - s.SpentCents
	if rem < 0 {
		return 0
	}
	return rem
}

// BudgetLoader loads the active budget snapshot for an org.
type BudgetLoader interface {
	LoadOrg(ctx context.Context, orgID uuid.UUID) (BudgetSnapshot, error)
}
