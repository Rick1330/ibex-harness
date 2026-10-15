package idempotency

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

type Ledger interface {
	Claim(ctx context.Context, principal Principal, key string, requestHash string) (ClaimOutcome, error)
	Finalize(ctx context.Context, claim ClaimToken, status int, response []byte) error
	Release(ctx context.Context, claim ClaimToken) error
}

type Principal struct{ OrgID, AgentID uuid.UUID }
type ClaimToken struct {
	ID               uuid.UUID
	Principal        Principal
	Key, RequestHash string
	Version          int64
}
type ClaimOutcome struct {
	Kind       ClaimKind
	Claim      ClaimToken
	Status     int
	Response   []byte
	RetryAfter time.Duration
}
type ClaimKind string

const (
	ClaimOwned      ClaimKind = "owned"
	ClaimReplay     ClaimKind = "replay"
	ClaimConflict   ClaimKind = "conflict"
	ClaimInProgress ClaimKind = "in_progress"
)

var (
	ErrInvalidLedgerClaim = errors.New("idempotency: invalid ledger claim")
	ErrLedgerConflict     = errors.New("idempotency: key used with a different request")
)

func HashRequest(b []byte) string { sum := sha256.Sum256(b); return hex.EncodeToString(sum[:]) }

type PostgresLedger struct {
	db    *sql.DB
	lease time.Duration
}

func NewPostgresLedger(db *sql.DB, lease time.Duration) (*PostgresLedger, error) {
	if db == nil {
		return nil, fmt.Errorf("idempotency: database is required")
	}
	if lease <= 0 {
		lease = 2 * time.Minute
	}
	return &PostgresLedger{db: db, lease: lease}, nil
}

// NewOptionalPostgresLedger preserves the intentionally disabled PostgreSQL profile.
func NewOptionalPostgresLedger(db *sql.DB, lease time.Duration) (Ledger, error) {
	if db == nil {
		return nil, nil
	}
	return NewPostgresLedger(db, lease)
}

type ledgerRow struct {
	id                 uuid.UUID
	requestHash, state string
	status             sql.NullInt64
	response           []byte
	expires            sql.NullTime
	version            int64
}

const insertLedgerSQL = `
INSERT INTO ibex_core.idempotency_ledger
 (organization_id, agent_id, dedupe_key, request_hash, state, lease_expires_at)
VALUES ($1, $2, $3, $4, 'claimed', NOW() + $5::interval)
ON CONFLICT (organization_id, agent_id, dedupe_key) DO NOTHING
RETURNING id, request_hash, state, status_code, response_payload, lease_expires_at, version`

type rowScanner interface{ Scan(dest ...any) error }

func scanLedgerRow(s rowScanner) (ledgerRow, error) {
	var row ledgerRow
	err := s.Scan(&row.id, &row.requestHash, &row.state, &row.status, &row.response, &row.expires, &row.version)
	return row, err
}

func validClaim(p Principal, key, requestHash string) bool {
	return p.OrgID != uuid.Nil && p.AgentID != uuid.Nil && strings.TrimSpace(key) != "" && strings.TrimSpace(requestHash) != "" && len(key) <= 256
}

func (l *PostgresLedger) Claim(ctx context.Context, p Principal, key, requestHash string) (ClaimOutcome, error) {
	key, requestHash = strings.TrimSpace(key), strings.TrimSpace(requestHash)
	if !validClaim(p, key, requestHash) {
		return ClaimOutcome{}, ErrInvalidLedgerClaim
	}
	tx, err := l.db.BeginTx(ctx, nil)
	if err != nil {
		return ClaimOutcome{}, err
	}
	defer func() { _ = tx.Rollback() }()
	if _, err = tx.ExecContext(ctx, `SELECT set_config('app.current_org_id', $1, true)`, p.OrgID.String()); err != nil {
		return ClaimOutcome{}, err
	}
	leaseArg := fmt.Sprintf("%f seconds", l.lease.Seconds())
	row, fresh, err := l.insertOrLoad(ctx, tx, p, key, requestHash)
	if err != nil {
		return ClaimOutcome{}, err
	}
	out, err := l.resolveClaim(ctx, tx, p, key, requestHash, leaseArg, row, fresh)
	if err != nil {
		return ClaimOutcome{}, err
	}
	if err := tx.Commit(); err != nil {
		return ClaimOutcome{}, err
	}
	return out, nil
}

func (l *PostgresLedger) insertOrLoad(ctx context.Context, tx *sql.Tx, p Principal, key, requestHash string) (ledgerRow, bool, error) {
	// Static SQL; every request-controlled value is passed through QueryRowContext arguments.
	row, err := scanLedgerRow(tx.QueryRowContext(ctx, insertLedgerSQL, // NOSONAR — static SQL with bound arguments.
		p.OrgID, p.AgentID, key, requestHash, fmt.Sprintf("%f seconds", l.lease.Seconds())))
	if err == nil {
		return row, true, nil
	}
	if !errors.Is(err, sql.ErrNoRows) {
		return ledgerRow{}, false, err
	}
	row, err = scanLedgerRow(tx.QueryRowContext(ctx, `
SELECT id, request_hash, state, status_code, response_payload, lease_expires_at, version
  FROM ibex_core.idempotency_ledger
 WHERE organization_id=$1 AND agent_id=$2 AND dedupe_key=$3 FOR UPDATE`, p.OrgID, p.AgentID, key))
	return row, false, err
}

func (l *PostgresLedger) resolveClaim(ctx context.Context, tx *sql.Tx, p Principal, key, requestHash, leaseArg string, row ledgerRow, fresh bool) (ClaimOutcome, error) {
	out := ClaimOutcome{Claim: ClaimToken{ID: row.id, Principal: p, Key: key, RequestHash: row.requestHash, Version: row.version}}
	if row.requestHash != requestHash {
		out.Kind = ClaimConflict
		return out, nil
	}
	if fresh {
		out.Kind = ClaimOwned
		return out, nil
	}
	if row.state == "finalized" {
		out.Kind, out.Status, out.Response = ClaimReplay, int(row.status.Int64), row.response
		return out, nil
	}
	if row.state != "claimed" || !row.expires.Valid {
		return ClaimOutcome{}, fmt.Errorf("idempotency: unsupported ledger state %q", row.state)
	}
	if row.expires.Time.After(time.Now().UTC()) {
		out.Kind, out.RetryAfter = ClaimInProgress, time.Until(row.expires.Time)
		return out, nil
	}
	row, err := scanLedgerRow(tx.QueryRowContext(ctx, `
UPDATE ibex_core.idempotency_ledger
   SET lease_expires_at=NOW()+$1::interval, version=version+1, updated_at=NOW()
 WHERE id=$2 AND organization_id=$3 AND agent_id=$4 AND dedupe_key=$5
   AND request_hash=$6 AND state='claimed' AND lease_expires_at <= NOW()
RETURNING id, request_hash, state, status_code, response_payload, lease_expires_at, version`, leaseArg, row.id, p.OrgID, p.AgentID, key, requestHash))
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			out.Kind, out.RetryAfter = ClaimInProgress, time.Second
			return out, nil
		}
		return ClaimOutcome{}, err
	}
	out.Kind, out.Claim.Version = ClaimOwned, row.version
	return out, nil
}

func (l *PostgresLedger) Finalize(ctx context.Context, claim ClaimToken, status int, response []byte) error {
	if !validClaim(claim.Principal, claim.Key, claim.RequestHash) || claim.ID == uuid.Nil || claim.Version <= 0 {
		return ErrInvalidLedgerClaim
	}
	tx, err := l.db.BeginTx(ctx, nil)
	if err != nil {
		return err
	}
	defer func() { _ = tx.Rollback() }()
	if _, err := tx.ExecContext(ctx, `SELECT set_config('app.current_org_id', $1, true)`, claim.Principal.OrgID.String()); err != nil {
		return err
	}
	res, err := tx.ExecContext(ctx, `UPDATE ibex_core.idempotency_ledger
   SET state='finalized', status_code=$1, response_payload=$2, lease_expires_at=NULL,
       version=version+1, updated_at=NOW()
 WHERE id=$3 AND organization_id=$4 AND agent_id=$5 AND dedupe_key=$6
   AND request_hash=$7 AND version=$8 AND state='claimed'`, status, response, claim.ID, claim.Principal.OrgID, claim.Principal.AgentID, claim.Key, claim.RequestHash, claim.Version)
	if err != nil {
		return err
	}
	n, err := res.RowsAffected()
	if err != nil {
		return err
	}
	if n != 1 {
		return fmt.Errorf("%w: claim is no longer owned", ErrLedgerConflict)
	}
	return tx.Commit()
}

// Release removes an owned in-flight claim so a transient operation can be retried.
// The claim token version fences stale owners from releasing a reclaimed claim.
func (l *PostgresLedger) Release(ctx context.Context, claim ClaimToken) error {
	if !validClaim(claim.Principal, claim.Key, claim.RequestHash) || claim.ID == uuid.Nil || claim.Version <= 0 {
		return ErrInvalidLedgerClaim
	}
	tx, err := l.db.BeginTx(ctx, nil)
	if err != nil {
		return err
	}
	defer func() { _ = tx.Rollback() }()
	if _, err := tx.ExecContext(ctx, `SELECT set_config('app.current_org_id', $1, true)`, claim.Principal.OrgID.String()); err != nil {
		return err
	}
	res, err := tx.ExecContext(ctx, `DELETE FROM ibex_core.idempotency_ledger
 WHERE id=$1 AND organization_id=$2 AND agent_id=$3 AND dedupe_key=$4
   AND request_hash=$5 AND version=$6 AND state='claimed'`,
		claim.ID, claim.Principal.OrgID, claim.Principal.AgentID, claim.Key, claim.RequestHash, claim.Version)
	if err != nil {
		return err
	}
	n, err := res.RowsAffected()
	if err != nil {
		return err
	}
	if n != 1 {
		return fmt.Errorf("%w: claim is no longer owned", ErrLedgerConflict)
	}
	return tx.Commit()
}
