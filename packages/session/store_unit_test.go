package session

import (
	"context"
	"database/sql"
	"errors"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/telemetry"
	"github.com/google/uuid"
	"github.com/lib/pq"
)

func TestUnit_NewPostgresStore(t *testing.T) {
	t.Parallel()

	if _, err := NewPostgresStore(PostgresStoreDeps{}); err == nil {
		t.Fatal("expected error for nil db")
	}

	db := openClosedPostgres(t)
	tracer := telemetry.NoopTracer("ibex-session")

	store, err := NewPostgresStore(PostgresStoreDeps{
		DB: db, Metrics: recordingMetrics{}, Tracer: tracer,
	})
	if err != nil {
		t.Fatalf("NewPostgresStore: %v", err)
	}
	if store == nil {
		t.Fatal("expected store")
	}

	if _, err := NewPostgresStore(PostgresStoreDeps{DB: db, Tracer: tracer}); err != nil {
		t.Fatalf("noop metrics: %v", err)
	}

	if _, err := NewPostgresStore(PostgresStoreDeps{DB: db}); err == nil {
		t.Fatal("expected error for nil tracer")
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

	if _, err := store.Complete(ctx, sessionID, orgID); err == nil {
		t.Fatal("Complete: expected begin error")
	}

	if _, err := store.AbandonIdle(ctx, AbandonIdleParams{
		IdleBefore: time.Now().UTC(),
	}); err == nil {
		t.Fatal("AbandonIdle: expected begin error")
	}
}

func TestUnit_ClampAbandonLimit(t *testing.T) {
	t.Parallel()
	cases := []struct {
		in, want int
	}{
		{in: 0, want: defaultAbandonIdleLimit},
		{in: -1, want: defaultAbandonIdleLimit},
		{in: 10, want: 10},
		{in: maxAbandonIdleLimit, want: maxAbandonIdleLimit},
		{in: maxAbandonIdleLimit + 100, want: maxAbandonIdleLimit},
	}
	for _, tc := range cases {
		if got := clampAbandonLimit(tc.in); got != tc.want {
			t.Fatalf("clampAbandonLimit(%d)=%d want %d", tc.in, got, tc.want)
		}
	}
}

func TestUnit_ValidateCheckpointStats(t *testing.T) {
	t.Parallel()

	base := CheckpointParams{
		SessionID: uuid.New(), OrgID: uuid.New(), TurnIndex: 1,
	}
	cases := []struct {
		name    string
		mutate  func(*CheckpointParams)
		wantErr bool
	}{
		{name: "negative_input", mutate: func(p *CheckpointParams) { p.InputTokens = -1 }, wantErr: true},
		{name: "negative_output", mutate: func(p *CheckpointParams) { p.OutputTokens = -1 }, wantErr: true},
		{name: "negative_latency", mutate: func(p *CheckpointParams) { p.LatencyMs = -1 }, wantErr: true},
		{name: "valid_zeros", mutate: func(*CheckpointParams) {}, wantErr: false},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			p := base
			tc.mutate(&p)
			err := validateCheckpointStats(p)
			if tc.wantErr && err == nil {
				t.Fatal("expected error")
			}
			if !tc.wantErr && err != nil {
				t.Fatalf("unexpected: %v", err)
			}
		})
	}
}

func TestUnit_AppendCheckpoint_RejectsNegativeStats(t *testing.T) {
	t.Parallel()

	store := mustClosedStore(t)
	err := store.AppendCheckpoint(context.Background(), CheckpointParams{
		SessionID: uuid.New(), OrgID: uuid.New(), AgentID: uuid.New(), TurnIndex: 0,
		RequestID: "r", MessagesHash: "h", Model: "m", Provider: "p",
		InputTokens: -1, LatencyMs: 1,
	})
	if err == nil {
		t.Fatal("expected validation error before DB begin")
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

	assertSessionScan(t, got, scanWant{
		id: id, orgID: orgID, agentID: agentID, ext: &ext, status: StatusActive,
		model: "gpt-4o", provider: "openai", dv: &dv,
		turns: 3, input: 10, output: 20, latency: 30,
	})
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

	assertSessionScan(t, got, scanWant{
		id: id, orgID: orgID, agentID: agentID, status: StatusActive, model: "m", provider: "p",
	})
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

	pqErr := &pq.Error{Code: uniqueViolationSQLState}
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
	}, &pq.Error{Code: uniqueViolationSQLState})
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
	id, orgID, agentID      uuid.UUID
	ext                     *string
	status, model, provider string
	dv                      *uuid.UUID
	turns                   int
	input, output, latency  int64
}

func assertSessionScan(t *testing.T, got *Session, want scanWant) {
	t.Helper()
	assertSessionIdentity(t, got, want)
	assertSessionCounters(t, got, want)
	assertOptionalString(t, got.ExternalID, want.ext, "external_id")
	assertOptionalUUID(t, got.DirectiveVersionID, want.dv, "directive")
}

func assertSessionIdentity(t *testing.T, got *Session, want scanWant) {
	t.Helper()
	assertSessionID(t, got, want.id)
	if got.OrgID != want.orgID {
		t.Fatalf("org_id=%s want %s", got.OrgID, want.orgID)
	}
	if got.AgentID != want.agentID {
		t.Fatalf("agent_id=%s want %s", got.AgentID, want.agentID)
	}
	if got.Status != want.status {
		t.Fatalf("status=%s want %s", got.Status, want.status)
	}
	if got.Model != want.model {
		t.Fatalf("model=%s want %s", got.Model, want.model)
	}
	if got.Provider != want.provider {
		t.Fatalf("provider=%s want %s", got.Provider, want.provider)
	}
}

func assertSessionCounters(t *testing.T, got *Session, want scanWant) {
	t.Helper()
	if got.TurnCount != want.turns {
		t.Fatalf("turns=%d want %d", got.TurnCount, want.turns)
	}
	if got.TotalInputTokens != want.input {
		t.Fatalf("input=%d want %d", got.TotalInputTokens, want.input)
	}
	if got.TotalOutputTokens != want.output {
		t.Fatalf("output=%d want %d", got.TotalOutputTokens, want.output)
	}
	if got.TotalLatencyMs != want.latency {
		t.Fatalf("latency=%d want %d", got.TotalLatencyMs, want.latency)
	}
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
	store, err := NewPostgresStore(PostgresStoreDeps{
		DB: db, Tracer: telemetry.NoopTracer("ibex-session"),
	})
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
	// Close immediately so BeginTx fails; skip Cleanup to avoid double-close.
	//nolint:errcheck // intentional close of unused handle for closed-DB tests
	_ = db.Close()
	return db
}
