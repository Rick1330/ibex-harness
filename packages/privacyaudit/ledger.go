package privacyaudit

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"time"

	"github.com/google/uuid"
	"github.com/lib/pq"
)

// Querier is the subset of *sql.DB / *sql.Tx used by ledger loaders.
type Querier interface {
	QueryContext(ctx context.Context, query string, args ...any) (*sql.Rows, error)
}

// ResolveOrgs returns a single org when filter is set, else distinct ledger orgs.
func ResolveOrgs(ctx context.Context, q Querier, orgFilter string) ([]uuid.UUID, error) {
	if orgFilter != "" {
		id, err := uuid.Parse(orgFilter)
		if err != nil {
			return nil, fmt.Errorf("privacyaudit: org filter: %w", err)
		}
		return []uuid.UUID{id}, nil
	}
	return listDistinctOrgs(ctx, q)
}

func listDistinctOrgs(ctx context.Context, q Querier) ([]uuid.UUID, error) {
	rows, err := q.QueryContext(ctx, `
		SELECT DISTINCT org_id FROM ibex_core.privacy_audit_ledger ORDER BY org_id
	`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	return scanUUIDs(rows)
}

func scanUUIDs(rows *sql.Rows) ([]uuid.UUID, error) {
	var out []uuid.UUID
	for rows.Next() {
		var id uuid.UUID
		if err := rows.Scan(&id); err != nil {
			return nil, err
		}
		out = append(out, id)
	}
	return out, rows.Err()
}

// LoadEntries loads ledger rows for org ordered by seq ascending.
func LoadEntries(ctx context.Context, q Querier, org uuid.UUID) ([]Entry, error) {
	rows, err := q.QueryContext(ctx, `
		SELECT org_id, seq, prev_hash, row_hash,
		       actor_user_id, action, COALESCE(purpose,''), COALESCE(policy_result,''),
		       COALESCE(object_type,''), COALESCE(object_id,''), fields,
		       COALESCE(approval_ref,''), COALESCE(before_hash,''), COALESCE(after_hash,''),
		       COALESCE(correlation_id,''), COALESCE(request_id,''), payload, created_at
		FROM ibex_core.privacy_audit_ledger
		WHERE org_id = $1
		ORDER BY seq ASC
	`, org)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	return scanEntries(rows)
}

func scanEntries(rows *sql.Rows) ([]Entry, error) {
	var out []Entry
	for rows.Next() {
		e, err := scanEntry(rows)
		if err != nil {
			return nil, err
		}
		out = append(out, e)
	}
	return out, rows.Err()
}

func scanEntry(rows *sql.Rows) (Entry, error) {
	var e Entry
	var actor sql.NullString
	var fields pq.StringArray
	var payload []byte
	var created time.Time
	if err := rows.Scan(
		&e.OrgID, &e.Seq, &e.PrevHash, &e.RowHash,
		&actor, &e.Action, &e.Purpose, &e.PolicyResult,
		&e.ObjectType, &e.ObjectID, &fields,
		&e.ApprovalRef, &e.BeforeHash, &e.AfterHash,
		&e.CorrelationID, &e.RequestID, &payload, &created,
	); err != nil {
		return Entry{}, err
	}
	e.ActorUserID = parseOptionalUUID(actor)
	e.Fields = []string(fields)
	e.Payload = json.RawMessage(payload)
	e.CreatedAt = created
	return e, nil
}

func parseOptionalUUID(actor sql.NullString) *uuid.UUID {
	if !actor.Valid {
		return nil
	}
	id, err := uuid.Parse(actor.String)
	if err != nil {
		return nil
	}
	return &id
}

// VerifyOrg loads and verifies one org's chain.
func VerifyOrg(ctx context.Context, q Querier, org uuid.UUID) (int, error) {
	entries, err := LoadEntries(ctx, q, org)
	if err != nil {
		return 0, err
	}
	if err := VerifyChain(entries); err != nil {
		return len(entries), err
	}
	return len(entries), nil
}
