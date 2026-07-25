package session

import (
	"context"
	"database/sql"
	"fmt"

	"github.com/google/uuid"
	"go.opentelemetry.io/otel/trace"
)

// Store is the durable session/checkpoint data-access API used by proxy lifecycle
// wiring (m2.4.3) and any caller that needs create/checkpoint/complete semantics
// with org-scoped RLS applied on every write transaction.
type Store interface {
	GetOrCreate(ctx context.Context, p GetOrCreateParams) (*Session, error)
	AppendCheckpoint(ctx context.Context, p CheckpointParams) error
	Complete(ctx context.Context, sessionID, orgID uuid.UUID) error
}

// PostgresStore is the Postgres-backed Store implementation. Callers obtain it via
// NewPostgresStore and may keep the concrete type when they need package helpers
// in tests; production wiring typically holds the Store interface.
type PostgresStore struct {
	db      *sql.DB
	metrics Metrics
	tracer  trace.Tracer
}

// PostgresStoreDeps carries required and optional dependencies for NewPostgresStore.
// DB and Tracer are required; Metrics may be nil (defaults to NoopMetrics).
type PostgresStoreDeps struct {
	DB      *sql.DB
	Metrics Metrics
	Tracer  trace.Tracer
}

// NewPostgresStore constructs a Postgres-backed Store.
// It fails when DB or Tracer is nil so production never falls back to a global tracer.
func NewPostgresStore(deps PostgresStoreDeps) (*PostgresStore, error) {
	if deps.DB == nil {
		return nil, fmt.Errorf("session: db is required")
	}
	if deps.Tracer == nil {
		return nil, fmt.Errorf("session: tracer is required")
	}
	metrics := deps.Metrics
	if metrics == nil {
		metrics = NoopMetrics{}
	}
	return &PostgresStore{db: deps.DB, metrics: metrics, tracer: deps.Tracer}, nil
}
