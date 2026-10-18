// Package budgetledger owns the durable admission-hold ledger behind the
// proxy hard-cap enforcement (GAP-006, provisional budget-reservation.v1
// slice). A hold exists only while the organization has an active hard_cap
// budget period; organizations without hard caps need no reservation and the
// claim returns ClaimNoCap. All failures fail closed: callers must never
// admit a request when the ledger is unavailable.
package budgetledger

import (
	"context"
	"crypto/sha256"
	"database/sql"
	"encoding/hex"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/google/uuid"
)

// DefaultLease bounds how long a claimed hold survives without finalize or
// release; sized to cover the longest expected provider call, including
// streaming responses. The reaper expires stale claims only after an
// additional grace window, so a slow but live owner can still settle.
const DefaultLease = 15 * time.Minute

// Ledger is the reservation state machine used by the proxy and worker.
type Ledger interface {
	Claim(ctx context.Context, p Principal, req ClaimRequest) (ClaimOutcome, error)
	Finalize(ctx context.Context, claim Reservation, amountFinalCents int64, completeness Completeness) error
	Release(ctx context.Context, claim Reservation) error
}

// Principal scopes every reservation to an organization and agent.
type Principal struct {
	OrgID, AgentID uuid.UUID
}

// ClaimRequest carries one admission attempt.
type ClaimRequest struct {
	Key            string
	RequestHash    string
	EstimatedCents int64
}

// Completeness marks whether a finalized amount is measured or estimated.
type Completeness string

const (
	// CompletenessComplete means the final amount came from provider usage.
	CompletenessComplete Completeness = "complete"
	// CompletenessEstimated means the provider reported no usage and the
	// admission estimate is the best available final amount.
	CompletenessEstimated Completeness = "estimated"
)

// Valid reports whether the completeness marker is one of the schema values.
func (c Completeness) Valid() bool {
	return c == CompletenessComplete || c == CompletenessEstimated
}

// ClaimKind is the typed admission outcome.
type ClaimKind string

const (
	// ClaimOwned means the caller holds a fresh reservation.
	ClaimOwned ClaimKind = "owned"
	// ClaimInProgress means another owner holds the same key.
	ClaimInProgress ClaimKind = "in_progress"
	// ClaimConflict means the key was used with a different request payload.
	ClaimConflict ClaimKind = "conflict"
	// ClaimExceeded means the hold would push the active period past its cap.
	ClaimExceeded ClaimKind = "exceeded"
	// ClaimNoCap means the org has no active hard_cap period; no hold is needed.
	ClaimNoCap ClaimKind = "no_cap"
)

// Reservation identifies an owned hold for finalize/release fencing.
type Reservation struct {
	ID          uuid.UUID
	Principal   Principal
	Key         string
	RequestHash string
	PeriodID    uuid.UUID
	Version     int64
}

// ClaimOutcome is the result of an admission attempt.
type ClaimOutcome struct {
	Kind           ClaimKind
	Reservation    Reservation
	RetryAfter     time.Duration
	RemainingCents int64
}

// Typed ledger errors. Database and transport failures are returned raw and
// must be mapped to a fail-closed unavailable response by callers.
var (
	// ErrInvalidClaim rejects structurally invalid claims before any query.
	ErrInvalidClaim = errors.New("budgetledger: invalid reservation claim")
	// ErrClaimClosed means the reservation is finalized, released, expired,
	// or was reclaimed by a newer owner and can no longer be settled.
	ErrClaimClosed = errors.New("budgetledger: reservation is no longer owned")
)

// HashRequest fingerprints a canonical request payload (SHA-256 hex).
func HashRequest(b []byte) string {
	sum := sha256.Sum256(b)
	return hex.EncodeToString(sum[:])
}

// PostgresLedger stores holds in ibex_core.budget_reservations.
type PostgresLedger struct {
	db    *sql.DB
	lease time.Duration
}

// NewPostgresLedger builds the durable ledger; lease defaults to DefaultLease.
func NewPostgresLedger(db *sql.DB, lease time.Duration) (*PostgresLedger, error) {
	if db == nil {
		return nil, fmt.Errorf("budgetledger: database is required")
	}
	if lease <= 0 {
		lease = DefaultLease
	}
	return &PostgresLedger{db: db, lease: lease}, nil
}

// NewOptionalPostgresLedger preserves the intentionally disabled PostgreSQL
// profile: no database means no ledger, and callers fail closed only when the
// budget profile itself is enabled.
func NewOptionalPostgresLedger(db *sql.DB, lease time.Duration) (Ledger, error) {
	if db == nil {
		return nil, nil
	}
	return NewPostgresLedger(db, lease)
}

func validClaimRequest(p Principal, req ClaimRequest) bool {
	return p.OrgID != uuid.Nil && p.AgentID != uuid.Nil &&
		strings.TrimSpace(req.Key) != "" && len(req.Key) <= 256 &&
		strings.TrimSpace(req.RequestHash) != "" && req.EstimatedCents >= 0
}

func validReservation(claim Reservation) bool {
	return claim.ID != uuid.Nil && claim.Principal.OrgID != uuid.Nil && claim.Principal.AgentID != uuid.Nil &&
		strings.TrimSpace(claim.Key) != "" && strings.TrimSpace(claim.RequestHash) != ""
}

// activePeriod is the org's currently enforceable hard_cap window.
type activePeriod struct {
	id         uuid.UUID
	capCents   int64
	spentCents int64
}

// reservationRow is the persisted hold state loaded under FOR UPDATE.
type reservationRow struct {
	id          uuid.UUID
	requestHash string
	state       string
	lease       sql.NullTime
	version     int64
}

const advisoryLockSQL = `SELECT pg_advisory_xact_lock(hashtext('budget-reservation:' || $1::text))`

const activePeriodSQL = `
SELECT id, cap_cents, spent_cents_cached
  FROM ibex_billing.budget_periods
 WHERE org_id = $1
   AND period_start <= NOW()
   AND period_end > NOW()
   AND enforcement_mode = 'hard_cap'
 ORDER BY period_start DESC
 LIMIT 1`

const loadReservationSQL = `
SELECT id, request_hash, state, lease_expires_at, version
  FROM ibex_core.budget_reservations
 WHERE organization_id = $1 AND agent_id = $2 AND reservation_key = $3
 FOR UPDATE`

const activeHoldCentsSQL = `
SELECT COALESCE(SUM(amount_estimated_cents), 0)
  FROM ibex_core.budget_reservations
 WHERE organization_id = $1 AND budget_period_id = $2 AND state = 'claimed'
   AND lease_expires_at > NOW() AND id <> $3`

const insertReservationSQL = `
INSERT INTO ibex_core.budget_reservations
 (organization_id, agent_id, budget_period_id, reservation_key, request_hash, state,
  amount_estimated_cents, lease_expires_at)
VALUES ($1, $2, $3, $4, $5, 'claimed', $6, NOW() + $7::interval)
ON CONFLICT (organization_id, agent_id, reservation_key) DO NOTHING
RETURNING id, version`

const resetReservationSQL = `
UPDATE ibex_core.budget_reservations
   SET state = 'claimed', budget_period_id = $1, amount_estimated_cents = $2,
       amount_final_cents = NULL, finalized_completeness = NULL,
       lease_expires_at = NOW() + $3::interval, version = version + 1, updated_at = NOW()
 WHERE id = $4 AND organization_id = $5 AND agent_id = $6 AND reservation_key = $7 AND version = $8
RETURNING id, version`

const expireStaleClaimSQL = `
UPDATE ibex_core.budget_reservations
   SET state = 'expired', lease_expires_at = NULL, version = version + 1, updated_at = NOW()
 WHERE id = $1 AND organization_id = $2 AND agent_id = $3 AND reservation_key = $4
   AND version = $5 AND state = 'claimed'`

const finalizeReservationSQL = `
UPDATE ibex_core.budget_reservations
   SET state = 'finalized', amount_final_cents = $1, finalized_completeness = $2,
       lease_expires_at = NULL, version = version + 1, updated_at = NOW()
 WHERE id = $3 AND organization_id = $4 AND agent_id = $5 AND reservation_key = $6
   AND version = $7 AND state = 'claimed'`

const releaseReservationSQL = `
UPDATE ibex_core.budget_reservations
   SET state = 'released', lease_expires_at = NULL, version = version + 1, updated_at = NOW()
 WHERE id = $1 AND organization_id = $2 AND agent_id = $3 AND reservation_key = $4
   AND version = $5 AND state = 'claimed'`

const reservationStateSQL = `
SELECT state, amount_final_cents, finalized_completeness
  FROM ibex_core.budget_reservations
 WHERE id = $1 AND organization_id = $2 AND agent_id = $3 AND reservation_key = $4`

// Claim admits one request: acquire the per-org admission lock, resolve the
// existing key row, enforce the hard cap against live holds, and persist the
// hold in a single transaction.
func (l *PostgresLedger) Claim(ctx context.Context, p Principal, req ClaimRequest) (ClaimOutcome, error) {
	req.Key = strings.TrimSpace(req.Key)
	req.RequestHash = strings.TrimSpace(req.RequestHash)
	if !validClaimRequest(p, req) {
		return ClaimOutcome{}, ErrInvalidClaim
	}
	var out ClaimOutcome
	err := l.withOrgTx(ctx, p.OrgID, func(tx *sql.Tx) error {
		var err error
		out, err = l.claimInTx(ctx, tx, p, req)
		return err
	})
	if err != nil {
		return ClaimOutcome{}, err
	}
	return out, nil
}

// claimInTx is the serialized admission body: lock, period, key row, hold.
func (l *PostgresLedger) claimInTx(ctx context.Context, tx *sql.Tx, p Principal, req ClaimRequest) (ClaimOutcome, error) {
	if _, err := tx.ExecContext(ctx, advisoryLockSQL, p.OrgID.String()); err != nil {
		return ClaimOutcome{}, fmt.Errorf("budgetledger: admission lock: %w", err)
	}
	period, found, err := loadActivePeriod(ctx, tx, p.OrgID)
	if err != nil {
		return ClaimOutcome{}, err
	}
	if !found {
		return ClaimOutcome{Kind: ClaimNoCap}, nil
	}
	row, exists, err := loadReservation(ctx, tx, p, req.Key)
	if err != nil {
		return ClaimOutcome{}, err
	}
	if !exists {
		return claimFresh(ctx, tx, claimFreshParams{principal: p, req: req, period: period})
	}
	return l.resolveExisting(ctx, tx, claimResolution{principal: p, req: req, period: period, row: row})
}

// withOrgTx runs fn inside a transaction scoped to one organization and
// commits on success. Rollback is always attempted and never masks fn errors.
func (l *PostgresLedger) withOrgTx(ctx context.Context, orgID uuid.UUID, fn func(*sql.Tx) error) error {
	tx, err := l.db.BeginTx(ctx, nil)
	if err != nil {
		return err
	}
	defer func() { _ = tx.Rollback() }()
	if err := setOrgScope(ctx, tx, orgID); err != nil {
		return err
	}
	if err := fn(tx); err != nil {
		return err
	}
	return tx.Commit()
}

type claimResolution struct {
	principal Principal
	req       ClaimRequest
	period    activePeriod
	row       reservationRow
}

type claimFreshParams struct {
	principal Principal
	req       ClaimRequest
	period    activePeriod
}

func (l *PostgresLedger) resolveExisting(ctx context.Context, tx *sql.Tx, in claimResolution) (ClaimOutcome, error) {
	row := in.row
	if row.requestHash != in.req.RequestHash {
		return ClaimOutcome{Kind: ClaimConflict}, nil
	}
	if row.state == "claimed" && row.lease.Valid && row.lease.Time.After(time.Now().UTC()) {
		return ClaimOutcome{Kind: ClaimInProgress, RetryAfter: time.Until(row.lease.Time)}, nil
	}
	// Expired claim or terminal row: the key is reclaimable. Capacity is
	// enforced against every other live hold in the period.
	otherHolds, err := activeHoldCents(ctx, tx, in.principal, in.period.id, row.id)
	if err != nil {
		return ClaimOutcome{}, err
	}
	if in.period.spentCents+otherHolds+in.req.EstimatedCents > in.period.capCents {
		if err := expireStaleClaim(ctx, tx, in.principal, in.req.Key, row); err != nil {
			return ClaimOutcome{}, err
		}
		return exceededOutcome(in.period, otherHolds), nil
	}
	return l.resetHeldRow(ctx, tx, in, row)
}

func expireStaleClaim(ctx context.Context, tx *sql.Tx, p Principal, key string, row reservationRow) error {
	if row.state != "claimed" {
		return nil
	}
	if _, err := tx.ExecContext(ctx, expireStaleClaimSQL, row.id, p.OrgID, p.AgentID, key, row.version); err != nil {
		return fmt.Errorf("budgetledger: expire stale claim: %w", err)
	}
	return nil
}

func (l *PostgresLedger) resetHeldRow(ctx context.Context, tx *sql.Tx, in claimResolution, row reservationRow) (ClaimOutcome, error) {
	var id uuid.UUID
	var version int64
	err := tx.QueryRowContext(ctx, resetReservationSQL,
		in.period.id, in.req.EstimatedCents, leaseInterval(l.lease),
		row.id, in.principal.OrgID, in.principal.AgentID, in.req.Key, row.version).Scan(&id, &version)
	if err != nil {
		return ClaimOutcome{}, fmt.Errorf("budgetledger: reset reservation: %w", err)
	}
	return ownedOutcome(in.principal, in.req, in.period.id, id, version), nil
}

func claimFresh(ctx context.Context, tx *sql.Tx, in claimFreshParams) (ClaimOutcome, error) {
	holds, err := activeHoldCents(ctx, tx, in.principal, in.period.id, uuid.Nil)
	if err != nil {
		return ClaimOutcome{}, err
	}
	if in.period.spentCents+holds+in.req.EstimatedCents > in.period.capCents {
		return exceededOutcome(in.period, holds), nil
	}
	var id uuid.UUID
	var version int64
	err = tx.QueryRowContext(ctx, insertReservationSQL,
		in.principal.OrgID, in.principal.AgentID, in.period.id, in.req.Key, in.req.RequestHash,
		in.req.EstimatedCents, leaseInterval(0)).Scan(&id, &version)
	if errors.Is(err, sql.ErrNoRows) {
		// Defensive: the per-org admission lock makes this unreachable, but a
		// concurrent owner must never be admitted twice.
		return ClaimOutcome{Kind: ClaimInProgress, RetryAfter: time.Second}, nil
	}
	if err != nil {
		return ClaimOutcome{}, fmt.Errorf("budgetledger: insert reservation: %w", err)
	}
	return ownedOutcome(in.principal, in.req, in.period.id, id, version), nil
}

func ownedOutcome(p Principal, req ClaimRequest, periodID, id uuid.UUID, version int64) ClaimOutcome {
	return ClaimOutcome{Kind: ClaimOwned, Reservation: Reservation{
		ID: id, Principal: p, Key: req.Key, RequestHash: req.RequestHash,
		PeriodID: periodID, Version: version,
	}}
}

func exceededOutcome(period activePeriod, holds int64) ClaimOutcome {
	remaining := period.capCents - period.spentCents - holds
	if remaining < 0 {
		remaining = 0
	}
	return ClaimOutcome{Kind: ClaimExceeded, RemainingCents: remaining}
}

// Finalize records the settled amount and completeness marker. It is
// idempotent for an identical repeat; a reclaimed or terminal reservation
// fails with ErrClaimClosed and must be surfaced, never silently dropped.
func (l *PostgresLedger) Finalize(ctx context.Context, claim Reservation, amountFinalCents int64, completeness Completeness) error {
	if !validReservation(claim) || amountFinalCents < 0 || !completeness.Valid() {
		return ErrInvalidClaim
	}
	return l.settle(ctx, claim, func(tx *sql.Tx) (sql.Result, error) {
		return tx.ExecContext(ctx, finalizeReservationSQL, amountFinalCents, string(completeness),
			claim.ID, claim.Principal.OrgID, claim.Principal.AgentID, claim.Key, claim.Version)
	}, func(settled settledRow) bool {
		return settled.state == "finalized" && settled.finalCents.Valid &&
			settled.finalCents.Int64 == amountFinalCents &&
			settled.marker.Valid && settled.marker.String == string(completeness)
	})
}

// Release drops an owned hold without a finalized amount. It is idempotent
// for an identical repeat and fails with ErrClaimClosed otherwise.
func (l *PostgresLedger) Release(ctx context.Context, claim Reservation) error {
	if !validReservation(claim) {
		return ErrInvalidClaim
	}
	return l.settle(ctx, claim, func(tx *sql.Tx) (sql.Result, error) {
		return tx.ExecContext(ctx, releaseReservationSQL,
			claim.ID, claim.Principal.OrgID, claim.Principal.AgentID, claim.Key, claim.Version)
	}, func(settled settledRow) bool {
		return settled.state == "released"
	})
}

// settledRow is the persisted terminal state used for idempotent retries.
type settledRow struct {
	state      string
	finalCents sql.NullInt64
	marker     sql.NullString
}

func (l *PostgresLedger) settle(ctx context.Context, claim Reservation, exec func(*sql.Tx) (sql.Result, error), idempotent func(settledRow) bool) error {
	return l.withOrgTx(ctx, claim.Principal.OrgID, func(tx *sql.Tx) error {
		res, err := exec(tx)
		if err != nil {
			return err
		}
		n, err := res.RowsAffected()
		if err != nil {
			return err
		}
		if n == 1 {
			return nil
		}
		settled, err := loadReservationState(ctx, tx, claim)
		if err != nil {
			return err
		}
		if !idempotent(settled) {
			return fmt.Errorf("%w: state=%s", ErrClaimClosed, settled.state)
		}
		return nil
	})
}

func loadReservationState(ctx context.Context, tx *sql.Tx, claim Reservation) (settledRow, error) {
	var settled settledRow
	row := tx.QueryRowContext(ctx, reservationStateSQL,
		claim.ID, claim.Principal.OrgID, claim.Principal.AgentID, claim.Key)
	err := row.Scan(&settled.state, &settled.finalCents, &settled.marker)
	if errors.Is(err, sql.ErrNoRows) {
		return settledRow{}, fmt.Errorf("%w: row missing", ErrClaimClosed)
	}
	if err != nil {
		return settledRow{}, fmt.Errorf("budgetledger: load settled reservation: %w", err)
	}
	return settled, nil
}

func loadActivePeriod(ctx context.Context, tx *sql.Tx, orgID uuid.UUID) (activePeriod, bool, error) {
	var period activePeriod
	err := tx.QueryRowContext(ctx, activePeriodSQL, orgID).Scan(&period.id, &period.capCents, &period.spentCents)
	if errors.Is(err, sql.ErrNoRows) {
		return activePeriod{}, false, nil
	}
	if err != nil {
		return activePeriod{}, false, fmt.Errorf("budgetledger: load active period: %w", err)
	}
	return period, true, nil
}

func loadReservation(ctx context.Context, tx *sql.Tx, p Principal, key string) (reservationRow, bool, error) {
	var row reservationRow
	err := tx.QueryRowContext(ctx, loadReservationSQL, p.OrgID, p.AgentID, key).Scan(
		&row.id, &row.requestHash, &row.state, &row.lease, &row.version)
	if errors.Is(err, sql.ErrNoRows) {
		return reservationRow{}, false, nil
	}
	if err != nil {
		return reservationRow{}, false, fmt.Errorf("budgetledger: load reservation: %w", err)
	}
	return row, true, nil
}

func activeHoldCents(ctx context.Context, tx *sql.Tx, p Principal, periodID, excludeID uuid.UUID) (int64, error) {
	var cents int64
	err := tx.QueryRowContext(ctx, activeHoldCentsSQL, p.OrgID, periodID, excludeID).Scan(&cents)
	if err != nil {
		return 0, fmt.Errorf("budgetledger: sum active holds: %w", err)
	}
	return cents, nil
}

func leaseInterval(lease time.Duration) string {
	if lease <= 0 {
		lease = DefaultLease
	}
	return fmt.Sprintf("%f seconds", lease.Seconds())
}

func setOrgScope(ctx context.Context, tx *sql.Tx, orgID uuid.UUID) error {
	if _, err := tx.ExecContext(ctx, `SELECT set_config('app.current_org_id', $1, true)`, orgID.String()); err != nil {
		return fmt.Errorf("budgetledger: set org scope: %w", err)
	}
	return nil
}
