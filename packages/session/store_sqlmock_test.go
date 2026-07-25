package session

import (
	"context"
	"database/sql"
	"errors"
	"testing"

	"github.com/DATA-DOG/go-sqlmock"
	"github.com/google/uuid"
	"github.com/lib/pq"
)

func TestUnit_StoreSQLMockPaths(t *testing.T) {
	t.Parallel()
	for _, tc := range storeSQLMockCases() {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			db, mock, store := newSQLMockStore(t)
			t.Cleanup(func() { _ = db.Close() })
			ids := newMockIDs()
			tc.setup(mock, ids)
			tc.run(t, store, ids)
			assertMockDone(t, mock)
		})
	}
}

type mockIDs struct {
	orgID, agentID, sessionID uuid.UUID
}

func newMockIDs() mockIDs {
	return mockIDs{orgID: uuid.New(), agentID: uuid.New(), sessionID: uuid.New()}
}

type storeSQLMockCase struct {
	name  string
	setup func(sqlmock.Sqlmock, mockIDs)
	run   func(*testing.T, *PostgresStore, mockIDs)
}

func storeSQLMockCases() []storeSQLMockCase {
	return []storeSQLMockCase{
		{name: "get_or_create_creates", setup: expectCreateSession, run: runGetOrCreateOK},
		{name: "get_or_create_existing", setup: expectExistingSession, run: runGetOrCreateOK},
		{name: "get_or_create_empty_ext", setup: expectEmptyExternalInsert, run: runGetOrCreateEmpty},
		{name: "get_or_create_unique_race", setup: expectUniqueRace, run: runGetOrCreateOK},
		{name: "get_or_create_rls_fail", setup: expectRLSFail, run: runGetOrCreateErr},
		{name: "get_or_create_lookup_fail", setup: expectLookupFail, run: runGetOrCreateErr},
		{name: "get_or_create_commit_fail", setup: expectExistingCommitFail, run: runGetOrCreateErr},
		{name: "get_or_create_race_missing", setup: expectUniqueRaceMissing, run: runGetOrCreateErr},
		{name: "checkpoint_ok", setup: expectCheckpointOK, run: runCheckpointOK},
		{name: "checkpoint_duplicate", setup: expectCheckpointDup, run: runCheckpointDup},
		{name: "checkpoint_missing", setup: expectCheckpointMissing, run: runCheckpointMissing},
		{name: "checkpoint_insert_err", setup: expectCheckpointInsertErr, run: runCheckpointErr},
		{name: "complete_active", setup: expectCompleteActive, run: runCompleteOK},
		{name: "complete_noop", setup: expectCompleteNoop, run: runCompleteOK},
		{name: "complete_race_noop", setup: expectCompleteRaceNoop, run: runCompleteOK},
		{name: "complete_not_found", setup: expectCompleteNotFound, run: runCompleteNotFound},
		{name: "complete_still_active", setup: expectCompleteStillActive, run: runCompleteNotFound},
	}
}

func beginWithRLS(mock sqlmock.Sqlmock, orgID uuid.UUID) {
	mock.ExpectBegin()
	mock.ExpectExec("set_config\\('app.current_org_id'").
		WithArgs(orgID.String()).
		WillReturnResult(sqlmock.NewResult(0, 0))
}

func expectCreateSession(mock sqlmock.Sqlmock, ids mockIDs) {
	beginWithRLS(mock, ids.orgID)
	mock.ExpectQuery("FROM ibex_core.sessions").
		WithArgs(ids.orgID, ids.agentID, "ext").
		WillReturnError(sql.ErrNoRows)
	mock.ExpectQuery("INSERT INTO ibex_core.sessions").
		WithArgs(ids.orgID, ids.agentID, "ext", "gpt-4o", "openai", nil, StatusActive).
		WillReturnRows(sessionRows(ids))
	mock.ExpectCommit()
}

func expectExistingSession(mock sqlmock.Sqlmock, ids mockIDs) {
	beginWithRLS(mock, ids.orgID)
	mock.ExpectQuery("FROM ibex_core.sessions").
		WithArgs(ids.orgID, ids.agentID, "ext").
		WillReturnRows(sessionRows(ids))
	mock.ExpectCommit()
}

func expectEmptyExternalInsert(mock sqlmock.Sqlmock, ids mockIDs) {
	beginWithRLS(mock, ids.orgID)
	mock.ExpectQuery("INSERT INTO ibex_core.sessions").
		WithArgs(ids.orgID, ids.agentID, nil, "gpt-4o", "openai", nil, StatusActive).
		WillReturnRows(sessionRows(ids))
	mock.ExpectCommit()
}

func expectUniqueRace(mock sqlmock.Sqlmock, ids mockIDs) {
	beginWithRLS(mock, ids.orgID)
	mock.ExpectQuery("FROM ibex_core.sessions").
		WithArgs(ids.orgID, ids.agentID, "ext").
		WillReturnError(sql.ErrNoRows)
	mock.ExpectQuery("INSERT INTO ibex_core.sessions").
		WithArgs(ids.orgID, ids.agentID, "ext", "gpt-4o", "openai", nil, StatusActive).
		WillReturnError(&pq.Error{Code: "23505"})
	mock.ExpectRollback()
	beginWithRLS(mock, ids.orgID)
	mock.ExpectQuery("FROM ibex_core.sessions").
		WithArgs(ids.orgID, ids.agentID, "ext").
		WillReturnRows(sessionRows(ids))
	mock.ExpectCommit()
}

func expectRLSFail(mock sqlmock.Sqlmock, ids mockIDs) {
	mock.ExpectBegin()
	mock.ExpectExec("set_config\\('app.current_org_id'").
		WithArgs(ids.orgID.String()).
		WillReturnError(errors.New("rls boom"))
	mock.ExpectRollback()
}

func expectLookupFail(mock sqlmock.Sqlmock, ids mockIDs) {
	beginWithRLS(mock, ids.orgID)
	mock.ExpectQuery("FROM ibex_core.sessions").
		WithArgs(ids.orgID, ids.agentID, "ext").
		WillReturnError(errors.New("lookup boom"))
	mock.ExpectRollback()
}

func expectExistingCommitFail(mock sqlmock.Sqlmock, ids mockIDs) {
	beginWithRLS(mock, ids.orgID)
	mock.ExpectQuery("FROM ibex_core.sessions").
		WithArgs(ids.orgID, ids.agentID, "ext").
		WillReturnRows(sessionRows(ids))
	mock.ExpectCommit().WillReturnError(errors.New("commit boom"))
}

func expectUniqueRaceMissing(mock sqlmock.Sqlmock, ids mockIDs) {
	beginWithRLS(mock, ids.orgID)
	mock.ExpectQuery("FROM ibex_core.sessions").
		WithArgs(ids.orgID, ids.agentID, "ext").
		WillReturnError(sql.ErrNoRows)
	mock.ExpectQuery("INSERT INTO ibex_core.sessions").
		WithArgs(ids.orgID, ids.agentID, "ext", "gpt-4o", "openai", nil, StatusActive).
		WillReturnError(&pq.Error{Code: "23505"})
	mock.ExpectRollback()
	beginWithRLS(mock, ids.orgID)
	mock.ExpectQuery("FROM ibex_core.sessions").
		WithArgs(ids.orgID, ids.agentID, "ext").
		WillReturnError(sql.ErrNoRows)
	mock.ExpectCommit()
}

func expectCheckpointOK(mock sqlmock.Sqlmock, ids mockIDs) {
	beginWithRLS(mock, ids.orgID)
	mock.ExpectExec("INSERT INTO ibex_core.checkpoints").
		WillReturnResult(sqlmock.NewResult(1, 1))
	mock.ExpectExec("UPDATE ibex_core.sessions").
		WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectCommit()
}

func expectCheckpointDup(mock sqlmock.Sqlmock, ids mockIDs) {
	beginWithRLS(mock, ids.orgID)
	mock.ExpectExec("INSERT INTO ibex_core.checkpoints").
		WillReturnError(&pq.Error{Code: "23505"})
	mock.ExpectRollback()
}

func expectCheckpointMissing(mock sqlmock.Sqlmock, ids mockIDs) {
	beginWithRLS(mock, ids.orgID)
	mock.ExpectExec("INSERT INTO ibex_core.checkpoints").
		WillReturnResult(sqlmock.NewResult(1, 1))
	mock.ExpectExec("UPDATE ibex_core.sessions").
		WillReturnResult(sqlmock.NewResult(0, 0))
	mock.ExpectRollback()
}

func expectCheckpointInsertErr(mock sqlmock.Sqlmock, ids mockIDs) {
	beginWithRLS(mock, ids.orgID)
	mock.ExpectExec("INSERT INTO ibex_core.checkpoints").
		WillReturnError(errors.New("insert boom"))
	mock.ExpectRollback()
}

func expectCompleteActive(mock sqlmock.Sqlmock, ids mockIDs) {
	beginWithRLS(mock, ids.orgID)
	mock.ExpectQuery("SELECT status FROM ibex_core.sessions").
		WithArgs(ids.sessionID, ids.orgID).
		WillReturnRows(statusRows(StatusActive))
	mock.ExpectExec("UPDATE ibex_core.sessions").
		WithArgs(StatusCompleted, ids.sessionID, ids.orgID, StatusActive).
		WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectCommit()
}

func expectCompleteNoop(mock sqlmock.Sqlmock, ids mockIDs) {
	beginWithRLS(mock, ids.orgID)
	mock.ExpectQuery("SELECT status FROM ibex_core.sessions").
		WithArgs(ids.sessionID, ids.orgID).
		WillReturnRows(statusRows(StatusAbandoned))
	mock.ExpectCommit()
}

func expectCompleteRaceNoop(mock sqlmock.Sqlmock, ids mockIDs) {
	beginWithRLS(mock, ids.orgID)
	mock.ExpectQuery("SELECT status FROM ibex_core.sessions").
		WithArgs(ids.sessionID, ids.orgID).
		WillReturnRows(statusRows(StatusActive))
	mock.ExpectExec("UPDATE ibex_core.sessions").
		WithArgs(StatusCompleted, ids.sessionID, ids.orgID, StatusActive).
		WillReturnResult(sqlmock.NewResult(0, 0))
	mock.ExpectQuery("SELECT status FROM ibex_core.sessions").
		WithArgs(ids.sessionID, ids.orgID).
		WillReturnRows(statusRows(StatusCompleted))
	mock.ExpectCommit()
}

func expectCompleteNotFound(mock sqlmock.Sqlmock, ids mockIDs) {
	beginWithRLS(mock, ids.orgID)
	mock.ExpectQuery("SELECT status FROM ibex_core.sessions").
		WithArgs(ids.sessionID, ids.orgID).
		WillReturnError(sql.ErrNoRows)
	mock.ExpectRollback()
}

func expectCompleteStillActive(mock sqlmock.Sqlmock, ids mockIDs) {
	beginWithRLS(mock, ids.orgID)
	mock.ExpectQuery("SELECT status FROM ibex_core.sessions").
		WithArgs(ids.sessionID, ids.orgID).
		WillReturnRows(statusRows(StatusActive))
	mock.ExpectExec("UPDATE ibex_core.sessions").
		WithArgs(StatusCompleted, ids.sessionID, ids.orgID, StatusActive).
		WillReturnResult(sqlmock.NewResult(0, 0))
	mock.ExpectQuery("SELECT status FROM ibex_core.sessions").
		WithArgs(ids.sessionID, ids.orgID).
		WillReturnRows(statusRows(StatusActive))
	mock.ExpectRollback()
}

func runGetOrCreateOK(t *testing.T, store *PostgresStore, ids mockIDs) {
	t.Helper()
	got, err := store.GetOrCreate(context.Background(), baseGetParams(ids, "ext"))
	if err != nil {
		t.Fatalf("GetOrCreate: %v", err)
	}
	if got.ID != ids.sessionID {
		t.Fatalf("id=%s", got.ID)
	}
}

func runGetOrCreateEmpty(t *testing.T, store *PostgresStore, ids mockIDs) {
	t.Helper()
	got, err := store.GetOrCreate(context.Background(), baseGetParams(ids, ""))
	if err != nil {
		t.Fatalf("GetOrCreate: %v", err)
	}
	if got.ID != ids.sessionID {
		t.Fatalf("id=%s", got.ID)
	}
}

func runGetOrCreateErr(t *testing.T, store *PostgresStore, ids mockIDs) {
	t.Helper()
	if _, err := store.GetOrCreate(context.Background(), baseGetParams(ids, "ext")); err == nil {
		t.Fatal("expected error")
	}
}

func runCheckpointOK(t *testing.T, store *PostgresStore, ids mockIDs) {
	t.Helper()
	if err := store.AppendCheckpoint(context.Background(), baseCheckpoint(ids)); err != nil {
		t.Fatalf("AppendCheckpoint: %v", err)
	}
}

func runCheckpointDup(t *testing.T, store *PostgresStore, ids mockIDs) {
	t.Helper()
	if err := store.AppendCheckpoint(context.Background(), baseCheckpoint(ids)); err != ErrDuplicateTurn {
		t.Fatalf("got %v", err)
	}
}

func runCheckpointMissing(t *testing.T, store *PostgresStore, ids mockIDs) {
	t.Helper()
	if err := store.AppendCheckpoint(context.Background(), baseCheckpoint(ids)); err != ErrNotFound {
		t.Fatalf("got %v", err)
	}
}

func runCheckpointErr(t *testing.T, store *PostgresStore, ids mockIDs) {
	t.Helper()
	if err := store.AppendCheckpoint(context.Background(), baseCheckpoint(ids)); err == nil {
		t.Fatal("expected error")
	}
}

func runCompleteOK(t *testing.T, store *PostgresStore, ids mockIDs) {
	t.Helper()
	if err := store.Complete(context.Background(), ids.sessionID, ids.orgID); err != nil {
		t.Fatalf("Complete: %v", err)
	}
}

func runCompleteNotFound(t *testing.T, store *PostgresStore, ids mockIDs) {
	t.Helper()
	if err := store.Complete(context.Background(), ids.sessionID, ids.orgID); err != ErrNotFound {
		t.Fatalf("got %v", err)
	}
}

func baseGetParams(ids mockIDs, ext string) GetOrCreateParams {
	return GetOrCreateParams{
		OrgID: ids.orgID, AgentID: ids.agentID, ExternalID: ext,
		Model: "gpt-4o", Provider: "openai",
	}
}

func baseCheckpoint(ids mockIDs) CheckpointParams {
	return CheckpointParams{
		SessionID: ids.sessionID, OrgID: ids.orgID, AgentID: ids.agentID, TurnIndex: 0,
		RequestID: "req", MessagesHash: "mh", InputTokens: 1, OutputTokens: 2,
		Model: "gpt-4o", Provider: "openai", LatencyMs: 5, IsComplete: true,
		CompletionHash: "ch", ProviderRequestID: "pr",
	}
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

func sessionRows(ids mockIDs) *sqlmock.Rows {
	return sqlmock.NewRows([]string{
		"id", "org_id", "agent_id", "external_id", "status", "model", "provider",
		"directive_version_id", "turn_count", "total_input_tokens",
		"total_output_tokens", "total_latency_ms",
	}).AddRow(ids.sessionID, ids.orgID, ids.agentID, "ext", StatusActive, "gpt-4o", "openai",
		nil, 0, 0, 0, 0)
}

func statusRows(status string) *sqlmock.Rows {
	return sqlmock.NewRows([]string{"status"}).AddRow(status)
}

func assertMockDone(t *testing.T, mock sqlmock.Sqlmock) {
	t.Helper()
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatalf("sqlmock: %v", err)
	}
}
