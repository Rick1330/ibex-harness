// Package fence implements the relay's authoritative lifecycle fence checks.
// The session fence check is a SECURITY DEFINER helper (migration 000047)
// owned by ibex_service; the relay role can execute it but cannot read
// ibex_core.sessions directly.
package fence

import (
	"context"
	"database/sql"
	"fmt"
	"strings"
	"time"

	"github.com/Rick1330/ibex-harness/packages/evidenceoutbox"
	ibexmetrics "github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/google/uuid"
)

// SessionResourceType is the only authoritative fence resource type supported
// in this round. Other producers' fenced rows fail closed as unsupported.
const SessionResourceType = "session"

// fenceOutcomes mirrors the SQL helper contract in migration 000047.
const (
	outcomeAlive      = "alive"
	outcomeTombstoned = "tombstoned"
	outcomeStale      = "stale_version"
	outcomeNotFound   = "not_found"
)

// SessionFenceChecker checks session tombstone/version fences against the
// authoritative PostgreSQL lifecycle row through the SECURITY DEFINER helper.
type SessionFenceChecker struct {
	db      *sql.DB
	metrics *ibexmetrics.RelayRegistry
}

// NewSessionFenceChecker constructs the checker. db and metrics are required.
func NewSessionFenceChecker(db *sql.DB, reg *ibexmetrics.RelayRegistry) (*SessionFenceChecker, error) {
	if db == nil {
		return nil, fmt.Errorf("relay fence: postgres db is required")
	}
	if reg == nil {
		return nil, fmt.Errorf("relay fence: metrics registry is required")
	}
	return &SessionFenceChecker{db: db, metrics: reg}, nil
}

// CheckFence implements clickhousesink.FenceChecker. It returns nil only when
// the authoritative fence reports the row alive; tombstoned, stale, missing,
// and unsupported resource types fail closed. Database errors are returned
// unwrapped from the terminal sentinels so the relay retries them.
func (c *SessionFenceChecker) CheckFence(ctx context.Context, orgID uuid.UUID, fence evidenceoutbox.TombstoneFence) error {
	start := time.Now()
	outcome, err := c.check(ctx, orgID, fence)
	c.metrics.ObserveFenceCheck(outcome, time.Since(start).Seconds())
	return err
}

func (c *SessionFenceChecker) check(ctx context.Context, orgID uuid.UUID, fence evidenceoutbox.TombstoneFence) (string, error) {
	if fence.ResourceType != SessionResourceType {
		return ibexmetrics.RelayFenceError, fmt.Errorf(
			"%w: resource_type %q", evidenceoutbox.ErrUnsupportedFenceResource, fence.ResourceType)
	}
	resourceID, err := uuid.Parse(strings.TrimSpace(fence.ResourceID))
	if err != nil || resourceID == uuid.Nil {
		return ibexmetrics.RelayFenceError, fmt.Errorf(
			"%w: session resource_id is not a uuid", evidenceoutbox.ErrUnsupportedFenceResource)
	}
	if orgID == uuid.Nil || fence.ResourceVersion <= 0 {
		return ibexmetrics.RelayFenceError, fmt.Errorf(
			"%w: invalid session fence identity", evidenceoutbox.ErrUnsupportedFenceResource)
	}

	var outcome string
	err = c.db.QueryRowContext(ctx,
		`SELECT ibex_core.evidence_outbox_check_session_fence($1, $2, $3)`,
		orgID, resourceID, fence.ResourceVersion,
	).Scan(&outcome)
	if err != nil {
		return ibexmetrics.RelayFenceError, fmt.Errorf("relay fence: check session fence: %w", err)
	}
	switch outcome {
	case outcomeAlive:
		return ibexmetrics.RelayFenceAlive, nil
	case outcomeTombstoned:
		return ibexmetrics.RelayFenceTombstoned, fmt.Errorf(
			"%w: session %s is soft-deleted", evidenceoutbox.ErrTombstonedResource, resourceID)
	case outcomeStale:
		return ibexmetrics.RelayFenceStale, fmt.Errorf(
			"%w: session %s version drift", evidenceoutbox.ErrTombstonedResource, resourceID)
	case outcomeNotFound:
		return ibexmetrics.RelayFenceNotFound, fmt.Errorf(
			"%w: session %s not found for org", evidenceoutbox.ErrTombstonedResource, resourceID)
	default:
		return ibexmetrics.RelayFenceError, fmt.Errorf(
			"relay fence: unexpected fence outcome %q", outcome)
	}
}
