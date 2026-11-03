package evidenceoutbox

import (
	"context"
	"errors"

	"github.com/google/uuid"
)

// ErrReconciliationNotProven means no matching durable outbox state could be
// verified. It is deliberately non-specific so callers do not expose storage
// details to an HTTP client.
var ErrReconciliationNotProven = errors.New("evidenceoutbox: durable reconciliation state not proven")

// ReconciliationProof records a verified PostgreSQL run and its outbox rows.
// It contains identities only; no payload or database error is exposed.
type ReconciliationProof struct {
	OrgID              uuid.UUID
	AgentID            *uuid.UUID
	SessionID          *uuid.UUID
	RequestID          string
	TraceID            string
	RunID              uuid.UUID
	OutboxIDs          []uuid.UUID
	RetryableOutboxIDs []uuid.UUID
}

// Matches reports whether the proof belongs to precisely this sanitized run
// and has a non-empty, internally consistent durable outbox identity set.
func (p ReconciliationProof) Matches(in RunInput) bool {
	return p.matchesIdentity(in) && validOutboxIDSets(p.OutboxIDs, p.RetryableOutboxIDs)
}

func (p ReconciliationProof) matchesIdentity(in RunInput) bool {
	return p.OrgID != uuid.Nil && p.OrgID == in.OrgID && p.RunID != uuid.Nil &&
		p.RequestID != "" && p.RequestID == in.RequestID &&
		p.TraceID != "" && p.TraceID == in.TraceID &&
		sameUUIDPtr(p.AgentID, in.AgentID) && sameUUIDPtr(p.SessionID, in.SessionID)
}

func validOutboxIDSets(allIDs, retryableIDs []uuid.UUID) bool {
	if len(allIDs) == 0 || hasDuplicateOrNilIDs(allIDs) {
		return false
	}
	all := make(map[uuid.UUID]struct{}, len(allIDs))
	for _, id := range allIDs {
		all[id] = struct{}{}
	}
	if hasDuplicateOrNilIDs(retryableIDs) {
		return false
	}
	for _, id := range retryableIDs {
		if _, exists := all[id]; !exists {
			return false
		}
	}
	return true
}

func hasDuplicateOrNilIDs(ids []uuid.UUID) bool {
	seen := make(map[uuid.UUID]struct{}, len(ids))
	for _, id := range ids {
		if id == uuid.Nil {
			return true
		}
		if _, duplicate := seen[id]; duplicate {
			return true
		}
		seen[id] = struct{}{}
	}
	return false
}

// HasDurableRetry is true only when at least one outbox row is in a state the
// relay can retry/recover (pending, failed, or in_flight) and the proof is
// otherwise valid for the associated request.
func (p ReconciliationProof) HasDurableRetry(in RunInput) bool {
	return p.Matches(in) && len(p.RetryableOutboxIDs) > 0
}

// AllDelivered is true when every verified outbox row is delivered. Such a
// reconciled commit is replay-safe success, not a degraded acknowledgement.
func (p ReconciliationProof) AllDelivered(in RunInput) bool {
	return p.Matches(in) && len(p.RetryableOutboxIDs) == 0
}

func sameUUIDPtr(a, b *uuid.UUID) bool {
	if a == nil || *a == uuid.Nil {
		return b == nil || *b == uuid.Nil
	}
	return b != nil && *b == *a
}

// ReconciliationSource can prove that a failed/ambiguous write committed and
// has durable relay state. Implementations must scope every query by org_id.
type ReconciliationSource interface {
	ReconcileRun(ctx context.Context, in RunInput) (ReconciliationProof, error)
}
