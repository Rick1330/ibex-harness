package session

import (
	"context"
	"database/sql"
	"testing"

	"github.com/DATA-DOG/go-sqlmock"
	"github.com/google/uuid"
	"github.com/lib/pq"
)

func TestUnit_GetOrCreate_Creates(t *testing.T) {
	t.Parallel()
	db, mock, store := newSQLMockStore(t)
	defer func() { _ = db.Close() }()

	orgID, agentID, sessionID := uuid.New(), uuid.New(), uuid.New()
	p := GetOrCreateParams{
		OrgID: orgID, AgentID: agentID, ExternalID: "ext-new",
		Model: "gpt-4o", Provider: "openai",
	}

	mock.ExpectBegin()
	expectSetOrgRLS(mock, orgID)
	mock.ExpectQuery("FROM ibex_core.sessions").
		WithArgs(orgID, agentID, "ext-new").
		WillReturnError(sql.ErrNoRows)
	mock.ExpectQuery("INSERT INTO ibex_core.sessions").
		WithArgs(orgID, agentID, "ext-new", "gpt-4o", "openai", nil, StatusActive).
		WillReturnRows(sessionRows(sessionID, orgID, agentID, "ext-new"))
	mock.ExpectCommit()

	got, err := store.GetOrCreate(context.Background(), p)
	if err != nil {
		t.Fatalf("GetOrCreate: %v", err)
	}
	if got.ID != sessionID {
		t.Fatalf("id=%s", got.ID)
	}
	assertMockDone(t, mock)
}

func TestUnit_GetOrCreate_Existing(t *testing.T) {
	t.Parallel()
	db, mock, store := newSQLMockStore(t)
	defer func() { _ = db.Close() }()

	orgID, agentID, sessionID := uuid.New(), uuid.New(), uuid.New()
	p := GetOrCreateParams{
		OrgID: orgID, AgentID: agentID, ExternalID: "ext-old",
		Model: "gpt-4o", Provider: "openai",
	}

	mock.ExpectBegin()
	expectSetOrgRLS(mock, orgID)
	mock.ExpectQuery("FROM ibex_core.sessions").
		WithArgs(orgID, agentID, "ext-old").
		WillReturnRows(sessionRows(sessionID, orgID, agentID, "ext-old"))
	mock.ExpectCommit()

	got, err := store.GetOrCreate(context.Background(), p)
	if err != nil {
		t.Fatalf("GetOrCreate: %v", err)
	}
	if got.ID != sessionID {
		t.Fatalf("id=%s", got.ID)
	}
	assertMockDone(t, mock)
}

func TestUnit_GetOrCreate_EmptyExternalAlwaysInserts(t *testing.T) {
	t.Parallel()
	db, mock, store := newSQLMockStore(t)
	defer func() { _ = db.Close() }()

	orgID, agentID, sessionID := uuid.New(), uuid.New(), uuid.New()
	p := GetOrCreateParams{
		OrgID: orgID, AgentID: agentID, ExternalID: "",
		Model: "gpt-4o", Provider: "openai",
	}

	mock.ExpectBegin()
	expectSetOrgRLS(mock, orgID)
	mock.ExpectQuery("INSERT INTO ibex_core.sessions").
		WithArgs(orgID, agentID, nil, "gpt-4o", "openai", nil, StatusActive).
		WillReturnRows(sessionRows(sessionID, orgID, agentID, ""))
	mock.ExpectCommit()

	got, err := store.GetOrCreate(context.Background(), p)
	if err != nil {
		t.Fatalf("GetOrCreate: %v", err)
	}
	if got.ID != sessionID {
		t.Fatalf("id=%s", got.ID)
	}
	assertMockDone(t, mock)
}

func TestUnit_GetOrCreate_UniqueRaceResolves(t *testing.T) {
	t.Parallel()
	db, mock, store := newSQLMockStore(t)
	defer func() { _ = db.Close() }()

	orgID, agentID, sessionID := uuid.New(), uuid.New(), uuid.New()
	p := GetOrCreateParams{
		OrgID: orgID, AgentID: agentID, ExternalID: "ext-race",
		Model: "gpt-4o", Provider: "openai",
	}

	mock.ExpectBegin()
	expectSetOrgRLS(mock, orgID)
	mock.ExpectQuery("FROM ibex_core.sessions").
		WithArgs(orgID, agentID, "ext-race").
		WillReturnError(sql.ErrNoRows)
	mock.ExpectQuery("INSERT INTO ibex_core.sessions").
		WithArgs(orgID, agentID, "ext-race", "gpt-4o", "openai", nil, StatusActive).
		WillReturnError(&pq.Error{Code: "23505"})
	mock.ExpectRollback()

	mock.ExpectBegin()
	expectSetOrgRLS(mock, orgID)
	mock.ExpectQuery("FROM ibex_core.sessions").
		WithArgs(orgID, agentID, "ext-race").
		WillReturnRows(sessionRows(sessionID, orgID, agentID, "ext-race"))
	mock.ExpectCommit()

	got, err := store.GetOrCreate(context.Background(), p)
	if err != nil {
		t.Fatalf("GetOrCreate: %v", err)
	}
	if got.ID != sessionID {
		t.Fatalf("id=%s", got.ID)
	}
	assertMockDone(t, mock)
}

func TestUnit_AppendCheckpoint_OK(t *testing.T) {
	t.Parallel()
	db, mock, store := newSQLMockStore(t)
	defer func() { _ = db.Close() }()

	orgID, agentID, sessionID := uuid.New(), uuid.New(), uuid.New()
	p := CheckpointParams{
		SessionID: sessionID, OrgID: orgID, AgentID: agentID, TurnIndex: 0,
		RequestID: "req", MessagesHash: "mh", InputTokens: 1, OutputTokens: 2,
		Model: "gpt-4o", Provider: "openai", LatencyMs: 5, IsComplete: true,
		CompletionHash: "ch", ProviderRequestID: "pr",
	}

	mock.ExpectBegin()
	expectSetOrgRLS(mock, orgID)
	mock.ExpectExec("INSERT INTO ibex_core.checkpoints").
		WithArgs(sessionID, orgID, agentID, 0, "req", "mh", 1, 2, "gpt-4o", "openai",
			"ch", 5, "pr", false, true).
		WillReturnResult(sqlmock.NewResult(1, 1))
	mock.ExpectExec("UPDATE ibex_core.sessions").
		WithArgs(1, 2, 5, sessionID, orgID).
		WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectCommit()

	if err := store.AppendCheckpoint(context.Background(), p); err != nil {
		t.Fatalf("AppendCheckpoint: %v", err)
	}
	assertMockDone(t, mock)
}

func TestUnit_AppendCheckpoint_Duplicate(t *testing.T) {
	t.Parallel()
	db, mock, store := newSQLMockStore(t)
	defer func() { _ = db.Close() }()

	orgID, agentID, sessionID := uuid.New(), uuid.New(), uuid.New()
	p := CheckpointParams{
		SessionID: sessionID, OrgID: orgID, AgentID: agentID, TurnIndex: 0,
		RequestID: "req", MessagesHash: "mh", Model: "gpt-4o", Provider: "openai",
		LatencyMs: 1, IsComplete: true,
	}

	mock.ExpectBegin()
	expectSetOrgRLS(mock, orgID)
	mock.ExpectExec("INSERT INTO ibex_core.checkpoints").
		WillReturnError(&pq.Error{Code: "23505"})
	mock.ExpectRollback()

	err := store.AppendCheckpoint(context.Background(), p)
	if err != ErrDuplicateTurn {
		t.Fatalf("got %v", err)
	}
	assertMockDone(t, mock)
}

func TestUnit_Complete_Active(t *testing.T) {
	t.Parallel()
	db, mock, store := newSQLMockStore(t)
	defer func() { _ = db.Close() }()

	orgID, sessionID := uuid.New(), uuid.New()
	mock.ExpectBegin()
	expectSetOrgRLS(mock, orgID)
	mock.ExpectQuery("SELECT status FROM ibex_core.sessions").
		WithArgs(sessionID, orgID).
		WillReturnRows(sqlmock.NewRows([]string{"status"}).AddRow(StatusActive))
	mock.ExpectExec("UPDATE ibex_core.sessions").
		WithArgs(StatusCompleted, sessionID, orgID, StatusActive).
		WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectCommit()

	if err := store.Complete(context.Background(), sessionID, orgID); err != nil {
		t.Fatalf("Complete: %v", err)
	}
	assertMockDone(t, mock)
}

func TestUnit_Complete_TerminalNoop(t *testing.T) {
	t.Parallel()
	db, mock, store := newSQLMockStore(t)
	defer func() { _ = db.Close() }()

	orgID, sessionID := uuid.New(), uuid.New()
	mock.ExpectBegin()
	expectSetOrgRLS(mock, orgID)
	mock.ExpectQuery("SELECT status FROM ibex_core.sessions").
		WithArgs(sessionID, orgID).
		WillReturnRows(sqlmock.NewRows([]string{"status"}).AddRow(StatusAbandoned))
	mock.ExpectCommit()

	if err := store.Complete(context.Background(), sessionID, orgID); err != nil {
		t.Fatalf("Complete: %v", err)
	}
	assertMockDone(t, mock)
}

func TestUnit_Complete_ConcurrentLoserNoop(t *testing.T) {
	t.Parallel()
	db, mock, store := newSQLMockStore(t)
	defer func() { _ = db.Close() }()

	orgID, sessionID := uuid.New(), uuid.New()
	mock.ExpectBegin()
	expectSetOrgRLS(mock, orgID)
	mock.ExpectQuery("SELECT status FROM ibex_core.sessions").
		WithArgs(sessionID, orgID).
		WillReturnRows(sqlmock.NewRows([]string{"status"}).AddRow(StatusActive))
	mock.ExpectExec("UPDATE ibex_core.sessions").
		WithArgs(StatusCompleted, sessionID, orgID, StatusActive).
		WillReturnResult(sqlmock.NewResult(0, 0))
	mock.ExpectQuery("SELECT status FROM ibex_core.sessions").
		WithArgs(sessionID, orgID).
		WillReturnRows(sqlmock.NewRows([]string{"status"}).AddRow(StatusCompleted))
	mock.ExpectCommit()

	if err := store.Complete(context.Background(), sessionID, orgID); err != nil {
		t.Fatalf("Complete: %v", err)
	}
	assertMockDone(t, mock)
}

func TestUnit_AppendCheckpoint_SessionMissing(t *testing.T) {
	t.Parallel()
	db, mock, store := newSQLMockStore(t)
	defer func() { _ = db.Close() }()

	orgID, agentID, sessionID := uuid.New(), uuid.New(), uuid.New()
	p := CheckpointParams{
		SessionID: sessionID, OrgID: orgID, AgentID: agentID, TurnIndex: 0,
		RequestID: "req", MessagesHash: "mh", Model: "gpt-4o", Provider: "openai",
		LatencyMs: 1, IsComplete: true,
	}

	mock.ExpectBegin()
	expectSetOrgRLS(mock, orgID)
	mock.ExpectExec("INSERT INTO ibex_core.checkpoints").
		WillReturnResult(sqlmock.NewResult(1, 1))
	mock.ExpectExec("UPDATE ibex_core.sessions").
		WillReturnResult(sqlmock.NewResult(0, 0))
	mock.ExpectRollback()

	err := store.AppendCheckpoint(context.Background(), p)
	if err != ErrNotFound {
		t.Fatalf("got %v", err)
	}
	assertMockDone(t, mock)
}

func newSQLMockStore(t *testing.T) (*sql.DB, sqlmock.Sqlmock, *PostgresStore) {
	t.Helper()
	db, mock, err := sqlmock.New(sqlmock.QueryMatcherOption(sqlmock.QueryMatcherRegexp))
	if err != nil {
		t.Fatalf("sqlmock: %v", err)
	}
	store, err := NewPostgresStore(PostgresStoreDeps{DB: db})
	if err != nil {
		t.Fatalf("store: %v", err)
	}
	return db, mock, store
}

func expectSetOrgRLS(mock sqlmock.Sqlmock, orgID uuid.UUID) {
	mock.ExpectExec("set_config\\('app.current_org_id'").
		WithArgs(orgID.String()).
		WillReturnResult(sqlmock.NewResult(0, 0))
}

func sessionRows(id, orgID, agentID uuid.UUID, ext string) *sqlmock.Rows {
	var extVal any
	if ext != "" {
		extVal = ext
	}
	return sqlmock.NewRows([]string{
		"id", "org_id", "agent_id", "external_id", "status", "model", "provider",
		"directive_version_id", "turn_count", "total_input_tokens",
		"total_output_tokens", "total_latency_ms",
	}).AddRow(id, orgID, agentID, extVal, StatusActive, "gpt-4o", "openai",
		nil, 0, 0, 0, 0)
}

func assertMockDone(t *testing.T, mock sqlmock.Sqlmock) {
	t.Helper()
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatalf("sqlmock: %v", err)
	}
}
