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
	"go.opentelemetry.io/otel"
)

// SessionResourceType is the only authoritative fence resource type supported
// in this round. Other producers' fenced rows fail closed as unsupported.
const SessionResourceType = "session"

// tracerName labels relay dependency spans.
const tracerName = "ibex-relay"

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
	ctx, span := otel.Tracer(tracerName).Start(ctx, "relay.fence.check")
	defer span.End()
	outcome, err := c.check(ctx, orgID, fence)
	c.metrics.ObserveFenceCheck(outcome, time.Since(start).Seconds())
	return err
}

func (c *SessionFenceChecker) check(ctx context.Context, orgID uuid.UUID, fence evidenceoutbox.TombstoneFence) (string, error) {
	resourceID, err := validatedSessionResourceID(fence)
	if err != nil {
		return ibexmetrics.RelayFenceError, err
	}
	if orgID == uuid.Nil {
		return ibexmetrics.RelayFenceError, fmt.Errorf(
			"%w: invalid session fence identity", evidenceoutbox.ErrUnsupportedFenceResource)
	}
	outcome, err := c.queryFenceOutcome(ctx, orgID, resourceID, fence.ResourceVersion)
	if err != nil {
		return ibexmetrics.RelayFenceError, err
	}
	return mapFenceOutcome(outcome, resourceID)
}

// validatedSessionResourceID fails closed for any fence that is not a
// well-formed session identity.
func validatedSessionResourceID(fence evidenceoutbox.TombstoneFence) (uuid.UUID, error) {
	if fence.ResourceType != SessionResourceType {
		return uuid.Nil, fmt.Errorf(
			"%w: resource_type %q", evidenceoutbox.ErrUnsupportedFenceResource, fence.ResourceType)
	}
	resourceID, err := uuid.Parse(strings.TrimSpace(fence.ResourceID))
	if err != nil || resourceID == uuid.Nil {
		return uuid.Nil, fmt.Errorf(
			"%w: session resource_id is not a uuid", evidenceoutbox.ErrUnsupportedFenceResource)
	}
	if fence.ResourceVersion <= 0 {
		return uuid.Nil, fmt.Errorf(
			"%w: invalid session fence identity", evidenceoutbox.ErrUnsupportedFenceResource)
	}
	return resourceID, nil
}

func (c *SessionFenceChecker) queryFenceOutcome(ctx context.Context, orgID, resourceID uuid.UUID, version int64) (string, error) {
	var outcome string
	if err := c.db.QueryRowContext(ctx,
		`SELECT ibex_core.evidence_outbox_check_session_fence($1, $2, $3)`,
		orgID, resourceID, version,
	).Scan(&outcome); err != nil {
		return "", fmt.Errorf("relay fence: check session fence: %w", err)
	}
	return outcome, nil
}

// mapFenceOutcome converts the helper's text outcome into the relay's terminal
// or retryable decision.
func mapFenceOutcome(outcome string, resourceID uuid.UUID) (string, error) {
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
