package modelpolicy

import (
	"context"
	"database/sql"
	"fmt"

	"github.com/google/uuid"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/trace"
)

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

	defaults, err := withOrgReadTx(ctx, s.db, orgID, func(tx *sql.Tx) (AgentDefaults, error) {
		return scanAgentDefaults(ctx, tx, orgID, agentID)
	})
	if err != nil {
		return AgentDefaults{}, recordStoreErr(span, err)
	}
	return defaults, nil
}

func scanAgentDefaults(
	ctx context.Context, tx *sql.Tx, orgID, agentID uuid.UUID,
) (AgentDefaults, error) {
	var model, provider sql.NullString
	err := tx.QueryRowContext(ctx, `
		SELECT default_model, default_provider
		FROM ibex_core.agents
		WHERE id = $1 AND org_id = $2`, agentID, orgID).Scan(&model, &provider)
	if err == sql.ErrNoRows {
		return AgentDefaults{}, nil
	}
	if err != nil {
		return AgentDefaults{}, fmt.Errorf("modelpolicy: agent defaults: %w", err)
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
