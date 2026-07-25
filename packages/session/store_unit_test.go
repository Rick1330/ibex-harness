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
	if err != nil || store == nil {
		t.Fatalf("store=%v err=%v", store, err)
	}
	if _, err := NewPostgresStore(PostgresStoreDeps{DB: db}); err != nil {
		t.Fatalf("noop metrics: %v", err)
	}
}

func TestUnit_ClosedDB_SurfaceBeginErrors(t *testing.T) {
	t.Parallel()
	store := mustClosedStore(t)
	ctx := context.Background()
	orgID, agentID, sessionID := uuid.New(), uuid.New(), uuid.New()
	if _, err := store.GetOrCreate(ctx, GetOrCreateParams{
		OrgID: orgID, AgentID: agentID, ExternalID: "ext", Model: "m", Provider: "p",
	}); err == nil {
		t.Fatal("GetOrCreate: expected begin error")
	}
	if err := store.AppendCheckpoint(ctx, CheckpointParams{
		SessionID: sessionID, OrgID: orgID, AgentID: agentID, TurnIndex: 0,
		RequestID: "r", MessagesHash: "h", Model: "m", Provider: "p", LatencyMs: 1,
	}); err == nil {
		t.Fatal("AppendCheckpoint: expected begin error")
	}
	if err := store.Complete(ctx, sessionID, orgID); err == nil {
		t.Fatal("Complete: expected begin error")
	}
}

func TestUnit_ScanSession_Populated(t *testing.T) {
	t.Parallel()
	id, orgID, agentID, dv := uuid.New(), uuid.New(), uuid.New(), uuid.New()
	ext := "ext-1"
	got, err := scanSession(fixedScanRow{
		id: id, orgID: orgID, agentID: agentID, ext: sql.NullString{String: ext, Valid: true},
		status: StatusActive, model: "gpt-4o", provider: "openai",
		directive: uuid.NullUUID{UUID: dv, Valid: true},
		turns:     3, inTok: 10, outTok: 20, latency: 30,
	})
	if err != nil {
		t.Fatalf("scan: %v", err)
	}
	assertSessionScan(t, got, scanWant{id: id, ext: &ext, dv: &dv})
}

func TestUnit_ScanSession_NullOptionals(t *testing.T) {
	t.Parallel()
	id, orgID, agentID := uuid.New(), uuid.New(), uuid.New()
	got, err := scanSession(fixedScanRow{
		id: id, orgID: orgID, agentID: agentID, status: StatusActive, model: "m", provider: "p",
	})
	if err != nil {
		t.Fatalf("scan: %v", err)
	}
	assertSessionScan(t, got, scanWant{id: id})
}

func TestUnit_ScanSession_Error(t *testing.T) {
	t.Parallel()
	_, err := scanSession(errScanRow{err: errors.New("scan fail")})
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

type scanWant struct {
	id  uuid.UUID
	ext *string
	dv  *uuid.UUID
}

func assertSessionScan(t *testing.T, got *Session, want scanWant) {
	t.Helper()
	assertSessionID(t, got, want.id)
	assertOptionalString(t, got.ExternalID, want.ext, "external_id")
	assertOptionalUUID(t, got.DirectiveVersionID, want.dv, "directive")
}

func assertSessionID(t *testing.T, got *Session, want uuid.UUID) {
	t.Helper()
	if got.ID != want {
		t.Fatalf("id=%s want %s", got.ID, want)
	}
}

func assertOptionalString(t *testing.T, got, want *string, field string) {
	t.Helper()
	if (got == nil) != (want == nil) {
		t.Fatalf("%s=%v want %v", field, got, want)
	}
	if want != nil && *got != *want {
		t.Fatalf("%s=%s want %s", field, *got, *want)
	}
}

func assertOptionalUUID(t *testing.T, got, want *uuid.UUID, field string) {
	t.Helper()
	if (got == nil) != (want == nil) {
		t.Fatalf("%s=%v want %v", field, got, want)
	}
	if want != nil && *got != *want {
		t.Fatalf("%s=%s want %s", field, *got, *want)
	}
}

type recordingMetrics struct{}

func (recordingMetrics) IncSessionGetOrCreate(string)             {}
func (recordingMetrics) ObserveSessionGetOrCreateSeconds(float64) {}
func (recordingMetrics) IncSessionCheckpoint(string)              {}
func (recordingMetrics) IncSessionComplete(string)                {}

type fixedScanRow struct {
	id, orgID, agentID      uuid.UUID
	ext                     sql.NullString
	status, model, provider string
	directive               uuid.NullUUID
	turns                   int
	inTok, outTok, latency  int64
}

func (r fixedScanRow) Scan(dest ...any) error {
	ptrs := []any{
		&r.id, &r.orgID, &r.agentID, &r.ext, &r.status, &r.model, &r.provider,
		&r.directive, &r.turns, &r.inTok, &r.outTok, &r.latency,
	}
	for i := range dest {
		if err := assignScan(dest[i], ptrs[i]); err != nil {
			return err
		}
	}
	return nil
}

func assignScan(dest, src any) error {
	switch d := dest.(type) {
	case *uuid.UUID:
		*d = *src.(*uuid.UUID)
	case *string:
		*d = *src.(*string)
	case *int:
		*d = *src.(*int)
	case *int64:
		*d = *src.(*int64)
	case *sql.NullString:
		*d = *src.(*sql.NullString)
	case *uuid.NullUUID:
		*d = *src.(*uuid.NullUUID)
	default:
		return errors.New("unsupported dest")
	}
	return nil
}

type errScanRow struct{ err error }

func (r errScanRow) Scan(...any) error { return r.err }

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
