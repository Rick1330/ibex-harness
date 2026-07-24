package session

import (
	"context"
	"database/sql"
	"errors"
	"testing"

	"github.com/google/uuid"
	"github.com/lib/pq"
)

func TestUnit_NewPostgresStore(t *testing.T) {
	t.Parallel()
	if _, err := NewPostgresStore(PostgresStoreDeps{}); err == nil {
		t.Fatal("expected error for nil db")
	}
	db := openClosedPostgres(t)
	store, err := NewPostgresStore(PostgresStoreDeps{DB: db, Metrics: recordingMetrics{}})
	if err != nil {
		t.Fatalf("NewPostgresStore: %v", err)
	}
	if store == nil || store.db == nil {
		t.Fatal("expected store")
	}
	if _, err := NewPostgresStore(PostgresStoreDeps{DB: db}); err != nil {
		t.Fatalf("noop metrics store: %v", err)
	}
}

func TestUnit_ClosedDB_SurfaceBeginErrors(t *testing.T) {
	t.Parallel()
	store := mustClosedStore(t)
	ctx := context.Background()
	orgID := uuid.New()
	agentID := uuid.New()
	sessionID := uuid.New()

	_, err := store.GetOrCreate(ctx, GetOrCreateParams{
		OrgID: orgID, AgentID: agentID, ExternalID: "ext",
		Model: "gpt-4o", Provider: "openai",
	})
	if err == nil {
		t.Fatal("GetOrCreate: expected begin error")
	}

	err = store.AppendCheckpoint(ctx, CheckpointParams{
		SessionID: sessionID, OrgID: orgID, AgentID: agentID, TurnIndex: 0,
		RequestID: "r", MessagesHash: "h", Model: "gpt-4o", Provider: "openai",
		LatencyMs: 1, IsComplete: true, CompletionHash: "c", ProviderRequestID: "p",
	})
	if err == nil {
		t.Fatal("AppendCheckpoint: expected begin error")
	}

	err = store.Complete(ctx, sessionID, orgID)
	if err == nil {
		t.Fatal("Complete: expected begin error")
	}
}

func TestUnit_ScanSession(t *testing.T) {
	t.Parallel()
	id := uuid.New()
	orgID := uuid.New()
	agentID := uuid.New()
	dv := uuid.New()
	ext := "ext-1"

	got, err := scanSession(fakeSessionRow{
		values: []any{id, orgID, agentID, sql.NullString{String: ext, Valid: true},
			StatusActive, "gpt-4o", "openai", uuid.NullUUID{UUID: dv, Valid: true},
			3, int64(10), int64(20), int64(30)},
	})
	if err != nil {
		t.Fatalf("scan: %v", err)
	}
	if got.ID != id || got.ExternalID == nil || *got.ExternalID != ext {
		t.Fatalf("session: %+v", got)
	}
	if got.DirectiveVersionID == nil || *got.DirectiveVersionID != dv {
		t.Fatalf("directive: %+v", got.DirectiveVersionID)
	}

	got, err = scanSession(fakeSessionRow{
		values: []any{id, orgID, agentID, sql.NullString{}, StatusActive, "m", "p",
			uuid.NullUUID{}, 0, int64(0), int64(0), int64(0)},
	})
	if err != nil {
		t.Fatalf("scan nulls: %v", err)
	}
	if got.ExternalID != nil || got.DirectiveVersionID != nil {
		t.Fatalf("expected null optionals: %+v", got)
	}

	_, err = scanSession(fakeSessionRow{err: errors.New("scan fail")})
	if err == nil {
		t.Fatal("expected scan error")
	}
}

func TestUnit_ShouldRetryUniqueRace_PQ(t *testing.T) {
	t.Parallel()
	pqErr := &pq.Error{Code: "23505"}
	if !shouldRetryUniqueRace(pqErr, "ext") {
		t.Fatal("expected retry on unique violation with external_id")
	}
	if shouldRetryUniqueRace(pqErr, "") {
		t.Fatal("empty external_id must not retry")
	}
	if !isUniqueViolation(pqErr) {
		t.Fatal("expected unique violation")
	}
}

func TestUnit_ResolveUniqueRace_MissingRow(t *testing.T) {
	t.Parallel()
	store := mustClosedStore(t)
	_, _, err := store.resolveUniqueRace(context.Background(), GetOrCreateParams{
		OrgID: uuid.New(), AgentID: uuid.New(), ExternalID: "ext",
	}, &pq.Error{Code: "23505"})
	if err == nil {
		t.Fatal("expected lookup/begin error")
	}
}

func TestUnit_NoopMetrics_Callable(t *testing.T) {
	t.Parallel()
	var m NoopMetrics
	m.IncSessionGetOrCreate(ResultCreated)
	m.ObserveSessionGetOrCreateSeconds(0.01)
	m.IncSessionCheckpoint(ResultOK)
	m.IncSessionComplete(ResultNoop)
}

type recordingMetrics struct{}

func (recordingMetrics) IncSessionGetOrCreate(string)             {}
func (recordingMetrics) ObserveSessionGetOrCreateSeconds(float64) {}
func (recordingMetrics) IncSessionCheckpoint(string)              {}
func (recordingMetrics) IncSessionComplete(string)                {}

type fakeSessionRow struct {
	values []any
	err    error
}

func (r fakeSessionRow) Scan(dest ...any) error {
	if r.err != nil {
		return r.err
	}
	for i := range dest {
		switch d := dest[i].(type) {
		case *uuid.UUID:
			*d = r.values[i].(uuid.UUID)
		case *string:
			*d = r.values[i].(string)
		case *int:
			*d = r.values[i].(int)
		case *int64:
			*d = r.values[i].(int64)
		case *sql.NullString:
			*d = r.values[i].(sql.NullString)
		case *uuid.NullUUID:
			*d = r.values[i].(uuid.NullUUID)
		default:
			return errors.New("unsupported dest")
		}
	}
	return nil
}

func mustClosedStore(t *testing.T) *PostgresStore {
	t.Helper()
	db := openClosedPostgres(t)
	store, err := NewPostgresStore(PostgresStoreDeps{DB: db})
	if err != nil {
		t.Fatalf("store: %v", err)
	}
	return store
}

func openClosedPostgres(t *testing.T) *sql.DB {
	t.Helper()
	db, err := sql.Open("postgres", "postgres://127.0.0.1:1/nope?sslmode=disable&connect_timeout=1")
	if err != nil {
		t.Fatalf("open: %v", err)
	}
	t.Cleanup(func() { _ = db.Close() })
	_ = db.Close()
	return db
}
