package ratelimit

import (
	"context"
	"database/sql"
	"fmt"

	"github.com/google/uuid"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/trace"
)

// OverrideRow is one rate_limit_overrides row (agent_id nil = org-level).
type OverrideRow struct {
	OrgID             uuid.UUID
	AgentID           uuid.UUID // uuid.Nil for org-level
	RequestsPerMinute int64
}

// OrgOverrideSet is the DB override snapshot for one organization.
type OrgOverrideSet struct {
	OrgRPM   *int64 // nil = no org-level DB override
	AgentRPM map[uuid.UUID]int64
}

// ConfigStore loads rate_limit_overrides: per-org under RLS, full poll through
// the cross-tenant snapshot definer.
type ConfigStore struct {
	db     *sql.DB
	tracer trace.Tracer
}

// NewConfigStore constructs a ConfigStore backed by Postgres.
func NewConfigStore(db *sql.DB) (*ConfigStore, error) {
	if db == nil {
		return nil, fmt.Errorf("ratelimit: db is required")
	}
	return &ConfigStore{db: db, tracer: otel.Tracer("ibex-ratelimit")}, nil
}

// configStatement is one statement a load runs before its read, with the label
// its failure is reported under.
type configStatement struct {
	label string
	query string
	args  []any
}

type loadOverridesParams struct {
	spanName  string
	pre       []configStatement
	query     string
	queryArgs []any
}

// LoadOrg returns overrides for one org under app.current_org_id RLS.
//
// The capability logins are NOINHERIT and hold no table grant of their own, so
// the org GUC alone is not enough: the read runs as ibex_app for this
// transaction, exactly like packages/billing. Without the role pin a capability
// DSN fails the read with SQLSTATE 42501.
func (s *ConfigStore) LoadOrg(ctx context.Context, orgID uuid.UUID) (OrgOverrideSet, error) {
	set, err := s.loadOverrides(ctx, loadOverridesParams{
		spanName: "ConfigStore.LoadOrg",
		pre: []configStatement{
			{label: "set tenant role", query: `SET LOCAL ROLE ibex_app`},
			{
				label: "set rls",
				query: `SELECT set_config('app.current_org_id', $1, true)`,
				args:  []any{orgID.String()},
			},
		},
		query: `
		SELECT org_id, agent_id::text, requests_per_minute
		FROM ibex_core.rate_limit_overrides
		WHERE org_id = $1`,
		queryArgs: []any{orgID},
	})
	if err != nil {
		return OrgOverrideSet{}, err
	}
	return set[orgID], nil
}

// LoadAll returns all overrides for the full poll. It is genuinely
// cross-tenant, so it reads through the ibex_core.rate_limit_overrides_snapshot
// definer: the runtime login has EXECUTE on it and the tenant role does not.
// No role pin is used, because a pin would drop the caller to ibex_app and
// lose the definer's cross-tenant reach.
func (s *ConfigStore) LoadAll(ctx context.Context) (map[uuid.UUID]OrgOverrideSet, error) {
	return s.loadOverrides(ctx, loadOverridesParams{
		spanName: "ConfigStore.LoadAll",
		query: `
		SELECT org_id, agent_id, requests_per_minute
		FROM ibex_core.rate_limit_overrides_snapshot()`,
	})
}

func (s *ConfigStore) loadOverrides(ctx context.Context, p loadOverridesParams) (map[uuid.UUID]OrgOverrideSet, error) {
	ctx, span := s.tracer.Start(ctx, p.spanName,
		trace.WithAttributes(
			attribute.String("db.system", "postgresql"),
			attribute.String("db.operation", "SELECT"),
		),
	)
	defer span.End()

	tx, err := s.db.BeginTx(ctx, &sql.TxOptions{ReadOnly: true})
	if err != nil {
		return nil, recordConfigStoreErr(span, err)
	}
	defer func() { _ = tx.Rollback() }()

	if p.pre != nil {
		for _, statement := range p.pre {
			if _, err := tx.ExecContext(ctx, statement.query, statement.args...); err != nil {
				return nil, recordConfigStoreErr(
					span, fmt.Errorf("ratelimit: %s: %w", statement.label, err),
				)
			}
		}
	}
	set, err := scanOverrides(ctx, tx, p.query, p.queryArgs...)
	if err != nil {
		return nil, recordConfigStoreErr(span, err)
	}
	if err := tx.Commit(); err != nil {
		return nil, recordConfigStoreErr(span, err)
	}
	return set, nil
}

func scanOverrides(ctx context.Context, tx *sql.Tx, query string, args ...any) (map[uuid.UUID]OrgOverrideSet, error) {
	rows, err := tx.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, fmt.Errorf("ratelimit: query overrides: %w", err)
	}
	defer func() { _ = rows.Close() }()

	var scanned []overrideScan
	for rows.Next() {
		var row overrideScan
		if err := rows.Scan(&row.OrgID, &row.AgentNull, &row.RPM); err != nil {
			return nil, fmt.Errorf("ratelimit: scan override: %w", err)
		}
		scanned = append(scanned, row)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("ratelimit: override rows: %w", err)
	}
	return buildOverrideSets(scanned)
}

type overrideScan struct {
	OrgID     uuid.UUID
	AgentNull sql.NullString
	RPM       int64
}

func buildOverrideSets(rows []overrideScan) (map[uuid.UUID]OrgOverrideSet, error) {
	out := make(map[uuid.UUID]OrgOverrideSet)
	for _, row := range rows {
		if err := mergeOverrideRow(out, row); err != nil {
			return nil, err
		}
	}
	return out, nil
}

func mergeOverrideRow(out map[uuid.UUID]OrgOverrideSet, row overrideScan) error {
	cur := out[row.OrgID]
	if cur.AgentRPM == nil {
		cur.AgentRPM = make(map[uuid.UUID]int64)
	}
	if !row.AgentNull.Valid || row.AgentNull.String == "" {
		v := row.RPM
		cur.OrgRPM = &v
		out[row.OrgID] = cur
		return nil
	}
	agentID, err := uuid.Parse(row.AgentNull.String)
	if err != nil {
		return fmt.Errorf("ratelimit: agent_id: %w", err)
	}
	cur.AgentRPM[agentID] = row.RPM
	out[row.OrgID] = cur
	return nil
}

func recordConfigStoreErr(span trace.Span, err error) error {
	span.RecordError(err)
	span.SetStatus(codes.Error, err.Error())
	return err
}
