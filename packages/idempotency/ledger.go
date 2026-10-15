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

// Ledger is the durable admission boundary for one mutating HTTP operation.
// Implementations must scope keys by the complete principal tuple.
type Ledger interface {
	Claim(ctx context.Context, principal Principal, key string, requestHash string) (ClaimOutcome, error)
	Finalize(ctx context.Context, claim ClaimToken, status int, response []byte) error
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

// HashRequest returns the SHA-256 request hash used by handlers.
func HashRequest(b []byte) string { sum := sha256.Sum256(b); return hex.EncodeToString(sum[:]) }

// PostgresLedger implements request-idempotency-core.v1 using PostgreSQL row locks.
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

type ledgerRow struct {
	id          uuid.UUID
	requestHash string
	state       string
	status      sql.NullInt64
	response    []byte
	expires     sql.NullTime
	version     int64
}

type rowScanner interface{ Scan(dest ...any) error }

func scanLedgerRow(s rowScanner) (ledgerRow, error) {
	var row ledgerRow
	err := s.Scan(&row.id, &row.requestHash, &row.state, &row.status, &row.response, &row.expires, &row.version)
	return row, err
}

func (l *PostgresLedger) Claim(ctx context.Context, p Principal, key, requestHash string) (ClaimOutcome, error) {
	key = strings.TrimSpace(key)
	requestHash = strings.TrimSpace(requestHash)
	if p.OrgID == uuid.Nil || p.AgentID == uuid.Nil || key == "" || requestHash == "" || len(key) > 256 {
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
	row, err := scanLedgerRow(tx.QueryRowContext(ctx, `
INSERT INTO ibex_core.idempotency_ledger
 (organization_id, agent_id, dedupe_key, request_hash, state, lease_expires_at)
VALUES ($1, $2, $3, $4, 'claimed', NOW() + $5::interval)
ON CONFLICT (organization_id, agent_id, dedupe_key) DO NOTHING
RETURNING id, request_hash, state, status_code, response_payload, lease_expires_at, version`,
		p.OrgID, p.AgentID, key, requestHash, leaseArg))

	fresh := err == nil
	if err != nil && !errors.Is(err, sql.ErrNoRows) {
		return ClaimOutcome{}, err
	}
	if !fresh {
		row, err = scanLedgerRow(tx.QueryRowContext(ctx, `
SELECT id, request_hash, state, status_code, response_payload, lease_expires_at, version
  FROM ibex_core.idempotency_ledger
 WHERE organization_id=$1 AND agent_id=$2 AND dedupe_key=$3
 FOR UPDATE`, p.OrgID, p.AgentID, key))
		if err != nil {
			return ClaimOutcome{}, err
		}
	}

	out := ClaimOutcome{Claim: ClaimToken{ID: row.id, Principal: p, Key: key, RequestHash: row.requestHash, Version: row.version}}
	switch {
	case row.requestHash != requestHash:
		out.Kind = ClaimConflict
	case fresh:
		out.Kind = ClaimOwned
	case row.state == "finalized":
		out.Kind, out.Status, out.Response = ClaimReplay, int(row.status.Int64), row.response
	case row.state == "claimed" && row.expires.Valid && row.expires.Time.After(time.Now().UTC()):
		out.Kind = ClaimInProgress
		out.RetryAfter = time.Until(row.expires.Time)
	case row.state == "claimed" && row.expires.Valid:
		row, err = scanLedgerRow(tx.QueryRowContext(ctx, `
UPDATE ibex_core.idempotency_ledger
   SET lease_expires_at=NOW()+$1::interval, version=version+1, updated_at=NOW()
 WHERE id=$2 AND organization_id=$3 AND agent_id=$4 AND dedupe_key=$5
   AND request_hash=$6 AND state='claimed' AND lease_expires_at <= NOW()
RETURNING id, request_hash, state, status_code, response_payload, lease_expires_at, version`,
			leaseArg, row.id, p.OrgID, p.AgentID, key, requestHash))
		if err != nil {
			return ClaimOutcome{}, err
		}
		out.Kind = ClaimOwned
		out.Claim.Version = row.version
	default:
		return ClaimOutcome{}, fmt.Errorf("idempotency: unsupported ledger state %q", row.state)
	}
	if err := tx.Commit(); err != nil {
		return ClaimOutcome{}, err
	}
	return out, nil
}

func (l *PostgresLedger) Finalize(ctx context.Context, claim ClaimToken, status int, response []byte) error {
	if claim.ID == uuid.Nil || claim.Principal.OrgID == uuid.Nil || claim.Principal.AgentID == uuid.Nil || strings.TrimSpace(claim.Key) == "" || claim.RequestHash == "" || claim.Version <= 0 {
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
   AND request_hash=$7 AND version=$8 AND state='claimed'`,
		status, response, claim.ID, claim.Principal.OrgID, claim.Principal.AgentID, claim.Key, claim.RequestHash, claim.Version)
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
