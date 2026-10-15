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
	ErrLedgerInProgress   = errors.New("idempotency: request is already in progress")
)

// HashRequest returns the canonical SHA-256 request hash used by handlers.
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
	_, err = tx.ExecContext(ctx, `SELECT set_config('app.current_org_id', $1, true)`, p.OrgID.String())
	if err != nil {
		return ClaimOutcome{}, err
	}
	var id uuid.UUID
	var storedHash, state string
	var status sql.NullInt64
	var response []byte
	var expires time.Time
	err = tx.QueryRowContext(ctx, `
INSERT INTO ibex_core.idempotency_ledger
 (organization_id, agent_id, dedupe_key, request_hash, state, lease_expires_at)
VALUES ($1, $2, $3, $4, 'claimed', NOW() + $5::interval)
ON CONFLICT (organization_id, agent_id, dedupe_key) DO UPDATE SET
 state = CASE WHEN ibex_core.idempotency_ledger.state = 'claimed'
                   AND ibex_core.idempotency_ledger.lease_expires_at <= NOW() THEN 'claimed'
              ELSE ibex_core.idempotency_ledger.state END,
 request_hash = CASE WHEN ibex_core.idempotency_ledger.state = 'claimed'
                   AND ibex_core.idempotency_ledger.lease_expires_at <= NOW() THEN EXCLUDED.request_hash
              ELSE ibex_core.idempotency_ledger.request_hash END,
 lease_expires_at = CASE WHEN ibex_core.idempotency_ledger.state = 'claimed'
                   AND ibex_core.idempotency_ledger.lease_expires_at <= NOW() THEN EXCLUDED.lease_expires_at
              ELSE ibex_core.idempotency_ledger.lease_expires_at END,
 updated_at = NOW()
RETURNING id, request_hash, state, status_code, response_payload, lease_expires_at`,
		p.OrgID, p.AgentID, key, requestHash, fmt.Sprintf("%f seconds", l.lease.Seconds())).
		Scan(&id, &storedHash, &state, &status, &response, &expires)
	if err != nil {
		return ClaimOutcome{}, err
	}
	out := ClaimOutcome{Claim: ClaimToken{ID: id, Principal: p, Key: key, RequestHash: storedHash}}
	switch {
	case storedHash != requestHash:
		out.Kind = ClaimConflict
	case state == "finalized":
		out.Kind, out.Status, out.Response = ClaimReplay, int(status.Int64), response
	case state == "claimed" && id != uuid.Nil && expires.After(time.Now().UTC()):
		out.Kind, out.RetryAfter = ClaimInProgress, time.Until(expires)
	default:
		out.Kind = ClaimOwned
		out.Claim.RequestHash = requestHash
	}
	if out.Kind == ClaimOwned {
		out.Claim.RequestHash = requestHash
	}
	if err := tx.Commit(); err != nil {
		return ClaimOutcome{}, err
	}
	return out, nil
}

func (l *PostgresLedger) Finalize(ctx context.Context, claim ClaimToken, status int, response []byte) error {
	if claim.ID == uuid.Nil || claim.Principal.OrgID == uuid.Nil || claim.Principal.AgentID == uuid.Nil || strings.TrimSpace(claim.Key) == "" || claim.RequestHash == "" {
		return ErrInvalidLedgerClaim
	}
	res, err := l.db.ExecContext(ctx, `UPDATE ibex_core.idempotency_ledger SET state='finalized', status_code=$1, response_payload=$2, lease_expires_at=NULL, version=version+1, updated_at=NOW() WHERE id=$3 AND organization_id=$4 AND agent_id=$5 AND dedupe_key=$6 AND request_hash=$7 AND state='claimed'`, status, response, claim.ID, claim.Principal.OrgID, claim.Principal.AgentID, claim.Key, claim.RequestHash)
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
	return nil
}
