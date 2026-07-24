package session

import (
	"context"
	"database/sql"
	"fmt"

	"github.com/google/uuid"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/trace"
)

// Store is the durable session/checkpoint data-access API.
type Store interface {
	GetOrCreate(ctx context.Context, p GetOrCreateParams) (*Session, error)
	AppendCheckpoint(ctx context.Context, p CheckpointParams) error
	Complete(ctx context.Context, sessionID, orgID uuid.UUID) error
}

// PostgresStore implements Store against ibex_core.sessions and checkpoints.
type PostgresStore struct {
	db      *sql.DB
	metrics Metrics
	tracer  trace.Tracer
}

// PostgresStoreDeps constructs a PostgresStore with optional metrics/tracer.
type PostgresStoreDeps struct {
	DB      *sql.DB
	Metrics Metrics
	Tracer  trace.Tracer
}

// NewPostgresStore constructs a Store backed by Postgres.
func NewPostgresStore(deps PostgresStoreDeps) (*PostgresStore, error) {
	if deps.DB == nil {
		return nil, fmt.Errorf("session: db is required")
	}
	metrics := deps.Metrics
	if metrics == nil {
		metrics = NoopMetrics{}
	}
	tracer := deps.Tracer
	if tracer == nil {
		tracer = otel.Tracer("ibex-session")
	}
	return &PostgresStore{db: deps.DB, metrics: metrics, tracer: tracer}, nil
}
