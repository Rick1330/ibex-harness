package modelpolicy

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

// PolicyLoader loads org model policies from Postgres (or a test fake).
type PolicyLoader interface {
	LoadOrg(ctx context.Context, orgID uuid.UUID) ([]Policy, error)
}

// Store loads org_model_policies with RLS org context.
type Store struct {
	db     *sql.DB
	tracer trace.Tracer
}

// NewStore constructs a Store backed by Postgres.
func NewStore(db *sql.DB) (*Store, error) {
	if db == nil {
		return nil, fmt.Errorf("modelpolicy: db is required")
	}
	return &Store{db: db, tracer: otel.Tracer("ibex-modelpolicy")}, nil
}

// LoadOrg returns policies for one org under app.current_org_id RLS, ordered by priority.
func (s *Store) LoadOrg(ctx context.Context, orgID uuid.UUID) ([]Policy, error) {
	ctx, span := s.tracer.Start(ctx, "Store.LoadOrg",
		trace.WithAttributes(
			attribute.String("db.system", "postgresql"),
			attribute.String("db.operation", "SELECT"),
			attribute.String("org.id", orgID.String()),
		),
	)
	defer span.End()

	policies, err := s.loadOrgTx(ctx, orgID)
	if err != nil {
		return nil, recordStoreErr(span, err)
	}
	return policies, nil
}

func (s *Store) loadOrgTx(ctx context.Context, orgID uuid.UUID) ([]Policy, error) {
	tx, err := s.db.BeginTx(ctx, &sql.TxOptions{ReadOnly: true})
	if err != nil {
		return nil, err
	}
	defer func() { _ = tx.Rollback() }()

	if err := setOrgRLS(ctx, tx, orgID); err != nil {
		return nil, err
	}
	out, err := scanOrgPolicies(ctx, tx, orgID)
	if err != nil {
		return nil, err
	}
	if err := tx.Commit(); err != nil {
		return nil, err
	}
	return out, nil
}

func setOrgRLS(ctx context.Context, tx *sql.Tx, orgID uuid.UUID) error {
	_, err := tx.ExecContext(ctx, `SELECT set_config('app.current_org_id', $1, true)`, orgID.String())
	if err != nil {
		return fmt.Errorf("modelpolicy: set rls: %w", err)
	}
	return nil
}

func scanOrgPolicies(ctx context.Context, tx *sql.Tx, orgID uuid.UUID) ([]Policy, error) {
	rows, err := tx.QueryContext(ctx, `
		SELECT id::text, org_id::text, model_pattern, allowed, priority
		FROM ibex_core.org_model_policies
		WHERE org_id = $1
		ORDER BY priority ASC, model_pattern ASC`, orgID)
	if err != nil {
		return nil, fmt.Errorf("modelpolicy: query: %w", err)
	}
	defer func() { _ = rows.Close() }()

	out := make([]Policy, 0)
	for rows.Next() {
		var p Policy
		if err := rows.Scan(&p.ID, &p.OrgID, &p.Pattern, &p.Allowed, &p.Priority); err != nil {
			return nil, fmt.Errorf("modelpolicy: scan: %w", err)
		}
		out = append(out, p)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	return out, nil
}

func recordStoreErr(span trace.Span, err error) error {
	span.RecordError(err)
	span.SetStatus(codes.Error, err.Error())
	return err
}

// AgentDefaults holds optional agent routing defaults from 4.A.3 columns.
type AgentDefaults struct {
	DefaultModel    string
	DefaultProvider string
}

// AgentDefaultLoader loads agents.default_model / default_provider.
type AgentDefaultLoader interface {
	Load(ctx context.Context, orgID, agentID uuid.UUID) (AgentDefaults, error)
}

// AgentStore reads agent default_model via Postgres RLS.
type AgentStore struct {
	db     *sql.DB
	tracer trace.Tracer
}

// NewAgentStore constructs an AgentStore.
func NewAgentStore(db *sql.DB) (*AgentStore, error) {
	if db == nil {
		return nil, fmt.Errorf("modelpolicy: db is required")
	}
	return &AgentStore{db: db, tracer: otel.Tracer("ibex-modelpolicy")}, nil
}

// Load returns default_model / default_provider for the agent (empty strings if unset).
func (s *AgentStore) Load(ctx context.Context, orgID, agentID uuid.UUID) (AgentDefaults, error) {
	ctx, span := s.tracer.Start(ctx, "AgentStore.Load",
		trace.WithAttributes(
			attribute.String("db.system", "postgresql"),
			attribute.String("org.id", orgID.String()),
			attribute.String("agent.id", agentID.String()),
		),
	)
	defer span.End()

	defaults, err := s.loadAgentDefaultsTx(ctx, orgID, agentID)
	if err != nil {
		return AgentDefaults{}, recordStoreErr(span, err)
	}
	return defaults, nil
}

func (s *AgentStore) loadAgentDefaultsTx(
	ctx context.Context, orgID, agentID uuid.UUID,
) (AgentDefaults, error) {
	tx, err := s.db.BeginTx(ctx, &sql.TxOptions{ReadOnly: true})
	if err != nil {
		return AgentDefaults{}, err
	}
	defer func() { _ = tx.Rollback() }()

	if err := setOrgRLS(ctx, tx, orgID); err != nil {
		return AgentDefaults{}, err
	}

	var model, provider sql.NullString
	err = tx.QueryRowContext(ctx, `
		SELECT default_model, default_provider
		FROM ibex_core.agents
		WHERE id = $1 AND org_id = $2`, agentID, orgID).Scan(&model, &provider)
	if err == sql.ErrNoRows {
		return AgentDefaults{}, nil
	}
	if err != nil {
		return AgentDefaults{}, fmt.Errorf("modelpolicy: agent defaults: %w", err)
	}
	if err := tx.Commit(); err != nil {
		return AgentDefaults{}, err
	}
	return AgentDefaults{
		DefaultModel:    nullStr(model),
		DefaultProvider: nullStr(provider),
	}, nil
}

func nullStr(v sql.NullString) string {
	if v.Valid {
		return v.String
	}
	return ""
}

// NoopAgentDefaults always returns empty defaults (tests / no Postgres).
type NoopAgentDefaults struct{}

// Load returns empty AgentDefaults.
func (NoopAgentDefaults) Load(context.Context, uuid.UUID, uuid.UUID) (AgentDefaults, error) {
	return AgentDefaults{}, nil
}
