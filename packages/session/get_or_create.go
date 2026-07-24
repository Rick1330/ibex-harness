package session

import (
	"context"
	"database/sql"
	"fmt"
	"time"

	"github.com/google/uuid"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/trace"
)

const selectSessionByExternalSQL = `
SELECT id, org_id, agent_id, external_id, status, model, provider,
       directive_version_id, turn_count, total_input_tokens,
       total_output_tokens, total_latency_ms
FROM ibex_core.sessions
WHERE org_id = $1::uuid AND agent_id = $2::uuid
  AND external_id = $3 AND deleted_at IS NULL
LIMIT 1`

const insertSessionSQL = `
INSERT INTO ibex_core.sessions
	(org_id, agent_id, external_id, model, provider, directive_version_id, status)
VALUES ($1::uuid, $2::uuid, $3, $4, $5, $6, $7)
RETURNING id, org_id, agent_id, external_id, status, model, provider,
          directive_version_id, turn_count, total_input_tokens,
          total_output_tokens, total_latency_ms`

// GetOrCreate returns an existing session for external_id or creates a new one.
func (s *PostgresStore) GetOrCreate(ctx context.Context, p GetOrCreateParams) (*Session, error) {
	start := time.Now()
	ctx, span := s.tracer.Start(ctx, "PostgresStore.GetOrCreate",
		trace.WithAttributes(
			attribute.String("db.system", "postgresql"),
			attribute.String("db.table", "ibex_core.sessions"),
			attribute.String("db.operation", "UPSERT"),
		),
	)
	defer span.End()

	sess, result, err := s.getOrCreate(ctx, p)
	s.metrics.ObserveSessionGetOrCreateSeconds(time.Since(start).Seconds())
	if err != nil {
		s.metrics.IncSessionGetOrCreate(ResultError)
		span.RecordError(err)
		span.SetStatus(codes.Error, err.Error())
		return nil, err
	}
	s.metrics.IncSessionGetOrCreate(result)
	return sess, nil
}

func (s *PostgresStore) getOrCreate(ctx context.Context, p GetOrCreateParams) (*Session, string, error) {
	sess, result, err := s.tryGetOrCreate(ctx, p)
	if !shouldRetryUniqueRace(err, p.ExternalID) {
		return sess, result, err
	}
	return s.resolveUniqueRace(ctx, p, err)
}

func shouldRetryUniqueRace(err error, externalID string) bool {
	if err == nil {
		return false
	}
	if externalID == "" {
		return false
	}
	return isUniqueViolation(err)
}

func (s *PostgresStore) resolveUniqueRace(ctx context.Context, p GetOrCreateParams, cause error) (*Session, string, error) {
	existing, lookupErr := s.lookupExternalFresh(ctx, p)
	if lookupErr != nil {
		return nil, "", lookupErr
	}
	if existing == nil {
		return nil, "", fmt.Errorf("session: unique race but row missing: %w", cause)
	}
	return existing, ResultExisting, nil
}

func (s *PostgresStore) tryGetOrCreate(ctx context.Context, p GetOrCreateParams) (*Session, string, error) {
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return nil, "", fmt.Errorf("session: begin get_or_create: %w", err)
	}
	defer func() { _ = tx.Rollback() }()

	if err := setOrgRLS(ctx, tx, p.OrgID); err != nil {
		return nil, "", err
	}
	existing, err := findExistingByExternal(ctx, tx, p)
	if err != nil {
		return nil, "", err
	}
	if existing != nil {
		return commitExisting(tx, existing)
	}
	return insertAndCommit(ctx, tx, p)
}

func findExistingByExternal(ctx context.Context, tx *sql.Tx, p GetOrCreateParams) (*Session, error) {
	if p.ExternalID == "" {
		return nil, nil
	}
	return lookupByExternalID(ctx, tx, p)
}

func commitExisting(tx *sql.Tx, existing *Session) (*Session, string, error) {
	if err := tx.Commit(); err != nil {
		return nil, "", fmt.Errorf("session: commit existing: %w", err)
	}
	return existing, ResultExisting, nil
}

func insertAndCommit(ctx context.Context, tx *sql.Tx, p GetOrCreateParams) (*Session, string, error) {
	created, err := insertSession(ctx, tx, p)
	if err != nil {
		return nil, "", err
	}
	if err := tx.Commit(); err != nil {
		return nil, "", fmt.Errorf("session: commit created: %w", err)
	}
	return created, ResultCreated, nil
}

func (s *PostgresStore) lookupExternalFresh(ctx context.Context, p GetOrCreateParams) (*Session, error) {
	tx, err := s.db.BeginTx(ctx, &sql.TxOptions{ReadOnly: true})
	if err != nil {
		return nil, fmt.Errorf("session: begin race lookup: %w", err)
	}
	defer func() { _ = tx.Rollback() }()
	if err := setOrgRLS(ctx, tx, p.OrgID); err != nil {
		return nil, err
	}
	existing, err := lookupByExternalID(ctx, tx, p)
	if err != nil {
		return nil, err
	}
	if err := tx.Commit(); err != nil {
		return nil, fmt.Errorf("session: commit race lookup: %w", err)
	}
	return existing, nil
}

func lookupByExternalID(ctx context.Context, tx *sql.Tx, p GetOrCreateParams) (*Session, error) {
	row := tx.QueryRowContext(ctx, selectSessionByExternalSQL, p.OrgID, p.AgentID, p.ExternalID)
	sess, err := scanSession(row)
	if err == sql.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, fmt.Errorf("session: lookup external_id: %w", err)
	}
	return sess, nil
}

func insertSession(ctx context.Context, tx *sql.Tx, p GetOrCreateParams) (*Session, error) {
	var ext any
	if p.ExternalID != "" {
		ext = p.ExternalID
	}
	row := tx.QueryRowContext(ctx, insertSessionSQL,
		p.OrgID, p.AgentID, ext, p.Model, p.Provider, p.DirectiveVersionID, StatusActive)
	sess, err := scanSession(row)
	if err != nil {
		return nil, fmt.Errorf("session: insert: %w", err)
	}
	return sess, nil
}

type sessionScanner interface {
	Scan(dest ...any) error
}

func scanSession(row sessionScanner) (*Session, error) {
	var (
		s                  Session
		externalID         sql.NullString
		directiveVersionID uuid.NullUUID
	)
	err := row.Scan(
		&s.ID, &s.OrgID, &s.AgentID, &externalID, &s.Status, &s.Model, &s.Provider,
		&directiveVersionID, &s.TurnCount, &s.TotalInputTokens,
		&s.TotalOutputTokens, &s.TotalLatencyMs,
	)
	if err != nil {
		return nil, err
	}
	if externalID.Valid {
		v := externalID.String
		s.ExternalID = &v
	}
	if directiveVersionID.Valid {
		v := directiveVersionID.UUID
		s.DirectiveVersionID = &v
	}
	return &s, nil
}
