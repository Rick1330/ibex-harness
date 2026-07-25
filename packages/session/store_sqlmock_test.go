package session

import (
	"context"
	"database/sql"
	"errors"
	"testing"
	"time"

	"github.com/DATA-DOG/go-sqlmock"
	"github.com/Rick1330/ibex-harness/packages/telemetry"
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
		{name: "abandon_idle_ok", setup: expectAbandonIdleOK, run: runAbandonIdleOK},
		{name: "abandon_idle_skip_lock", setup: expectAbandonIdleSkipLock, run: runAbandonIdleSkipLock},
		{name: "abandon_idle_empty", setup: expectAbandonIdleEmpty, run: runAbandonIdleEmpty},
		{name: "abandon_idle_sa_fail", setup: expectAbandonIdleSAFail, run: runAbandonIdleErr},
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
	expectSelectByExternal(mock, ids, nil, sql.ErrNoRows)
	mock.ExpectQuery("INSERT INTO ibex_core.sessions").
		WithArgs(ids.orgID, ids.agentID, sql.NullString{String: "ext", Valid: true},
			"gpt-4o", "openai", nil, StatusActive).
		WillReturnRows(sessionRows(ids))
	mock.ExpectCommit()
}

func expectExistingSession(mock sqlmock.Sqlmock, ids mockIDs) {
	beginWithRLS(mock, ids.orgID)
	expectSelectByExternal(mock, ids, sessionRows(ids), nil)
	mock.ExpectCommit()
}

func expectEmptyExternalInsert(mock sqlmock.Sqlmock, ids mockIDs) {
	beginWithRLS(mock, ids.orgID)
	mock.ExpectQuery("INSERT INTO ibex_core.sessions").
		WithArgs(ids.orgID, ids.agentID, sql.NullString{},
			"gpt-4o", "openai", nil, StatusActive).
		WillReturnRows(sessionRows(ids))
	mock.ExpectCommit()
}

func expectUniqueRace(mock sqlmock.Sqlmock, ids mockIDs) {
	expectConflictInsert(mock, ids)
	beginWithRLS(mock, ids.orgID)
	expectSelectByExternal(mock, ids, sessionRows(ids), nil)
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
	expectSelectByExternal(mock, ids, nil, errors.New("lookup boom"))
	mock.ExpectRollback()
}

func expectExistingCommitFail(mock sqlmock.Sqlmock, ids mockIDs) {
	beginWithRLS(mock, ids.orgID)
	expectSelectByExternal(mock, ids, sessionRows(ids), nil)
	mock.ExpectCommit().WillReturnError(errors.New("commit boom"))
}

func expectUniqueRaceMissing(mock sqlmock.Sqlmock, ids mockIDs) {
	expectConflictInsert(mock, ids)
	beginWithRLS(mock, ids.orgID)
	expectSelectByExternal(mock, ids, nil, sql.ErrNoRows)
	mock.ExpectCommit()
}

func expectConflictInsert(mock sqlmock.Sqlmock, ids mockIDs) {
	beginWithRLS(mock, ids.orgID)
	expectSelectByExternal(mock, ids, nil, sql.ErrNoRows)
	mock.ExpectQuery("INSERT INTO ibex_core.sessions").
		WithArgs(ids.orgID, ids.agentID, sql.NullString{String: "ext", Valid: true},
			"gpt-4o", "openai", nil, StatusActive).
		WillReturnError(&pq.Error{Code: "23505"})
	mock.ExpectRollback()
}

func expectSelectByExternal(mock sqlmock.Sqlmock, ids mockIDs, rows *sqlmock.Rows, err error) {
	q := mock.ExpectQuery("FROM ibex_core.sessions").WithArgs(ids.orgID, ids.agentID, "ext")
	if err != nil {
		q.WillReturnError(err)
		return
	}
	q.WillReturnRows(rows)
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
	expectSessionStatus(mock, ids, StatusActive, nil)
	mock.ExpectExec("UPDATE ibex_core.sessions").
		WithArgs(StatusCompleted, ids.sessionID, ids.orgID, StatusActive).
		WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectCommit()
}

func expectCompleteNoop(mock sqlmock.Sqlmock, ids mockIDs) {
	beginWithRLS(mock, ids.orgID)
	expectSessionStatus(mock, ids, StatusAbandoned, nil)
	mock.ExpectCommit()
}

func expectCompleteRaceNoop(mock sqlmock.Sqlmock, ids mockIDs) {
	expectCompleteZeroRowUpdate(mock, ids)
	expectSessionStatus(mock, ids, StatusCompleted, nil)
	mock.ExpectCommit()
}

func expectCompleteNotFound(mock sqlmock.Sqlmock, ids mockIDs) {
	beginWithRLS(mock, ids.orgID)
	expectSessionStatus(mock, ids, "", sql.ErrNoRows)
	mock.ExpectRollback()
}

func expectCompleteStillActive(mock sqlmock.Sqlmock, ids mockIDs) {
	expectCompleteZeroRowUpdate(mock, ids)
	expectSessionStatus(mock, ids, StatusActive, nil)
	mock.ExpectRollback()
}

func expectCompleteZeroRowUpdate(mock sqlmock.Sqlmock, ids mockIDs) {
	beginWithRLS(mock, ids.orgID)
	expectSessionStatus(mock, ids, StatusActive, nil)
	mock.ExpectExec("UPDATE ibex_core.sessions").
		WithArgs(StatusCompleted, ids.sessionID, ids.orgID, StatusActive).
		WillReturnResult(sqlmock.NewResult(0, 0))
}

func expectSessionStatus(mock sqlmock.Sqlmock, ids mockIDs, status string, err error) {
	q := mock.ExpectQuery("SELECT status FROM ibex_core.sessions").
		WithArgs(ids.sessionID, ids.orgID)
	if err != nil {
		q.WillReturnError(err)
		return
	}
	q.WillReturnRows(statusRows(status))
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
	err := store.AppendCheckpoint(context.Background(), baseCheckpoint(ids))
	if !errors.Is(err, ErrDuplicateTurn) {
		t.Fatalf("got %v", err)
	}
}

func runCheckpointMissing(t *testing.T, store *PostgresStore, ids mockIDs) {
	t.Helper()
	err := store.AppendCheckpoint(context.Background(), baseCheckpoint(ids))
	if !errors.Is(err, ErrNotFound) {
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
	err := store.Complete(context.Background(), ids.sessionID, ids.orgID)
	if !errors.Is(err, ErrNotFound) {
		t.Fatalf("got %v", err)
	}
}

func beginWithServiceAccount(mock sqlmock.Sqlmock) {
	mock.ExpectBegin()
	mock.ExpectExec("set_config\\('app.is_service_account'").
		WillReturnResult(sqlmock.NewResult(0, 0))
}

func expectAbandonIdleLock(mock sqlmock.Sqlmock, acquired bool) {
	beginWithServiceAccount(mock)
	mock.ExpectQuery("pg_try_advisory_xact_lock").
		WithArgs(SweepAdvisoryLockKey).
		WillReturnRows(sqlmock.NewRows([]string{"pg_try_advisory_xact_lock"}).AddRow(acquired))
}

func expectAbandonIdleVictims(mock sqlmock.Sqlmock, ids mockIDs, rows *sqlmock.Rows) {
	mock.ExpectQuery("WITH victims AS").
		WithArgs(StatusActive, sqlmock.AnyArg(), defaultAbandonIdleLimit, StatusAbandoned).
		WillReturnRows(rows)
}

func expectAbandonIdleOK(mock sqlmock.Sqlmock, ids mockIDs) {
	expectAbandonIdleLock(mock, true)
	ext := "ext"
	expectAbandonIdleVictims(mock, ids, sqlmock.NewRows([]string{"id", "org_id", "agent_id", "external_id"}).
		AddRow(ids.sessionID, ids.orgID, ids.agentID, ext))
	mock.ExpectCommit()
}

func expectAbandonIdleSkipLock(mock sqlmock.Sqlmock, ids mockIDs) {
	expectAbandonIdleLock(mock, false)
	mock.ExpectCommit()
}

func expectAbandonIdleEmpty(mock sqlmock.Sqlmock, ids mockIDs) {
	expectAbandonIdleLock(mock, true)
	expectAbandonIdleVictims(mock, ids, sqlmock.NewRows([]string{"id", "org_id", "agent_id", "external_id"}))
	mock.ExpectCommit()
}

func expectAbandonIdleSAFail(mock sqlmock.Sqlmock, ids mockIDs) {
	mock.ExpectBegin()
	mock.ExpectExec("set_config\\('app.is_service_account'").
		WillReturnError(errors.New("sa boom"))
	mock.ExpectRollback()
}

type abandonIdleExpect struct {
	skipped bool
	count   int
	wantErr bool
	checkID bool
}

func runAbandonIdleCase(t *testing.T, store *PostgresStore, ids mockIDs, want abandonIdleExpect) {
	t.Helper()
	res, err := store.AbandonIdle(context.Background(), AbandonIdleParams{
		IdleBefore: time.Now().UTC(),
	})
	if want.wantErr {
		if err == nil {
			t.Fatal("expected error")
		}
		return
	}
	if err != nil {
		t.Fatalf("AbandonIdle: %v", err)
	}
	if res.SkippedLock != want.skipped || res.Count() != want.count {
		t.Fatalf("res=%+v want skipped=%v count=%d", res, want.skipped, want.count)
	}
	if want.checkID && res.Abandoned[0].SessionID != ids.sessionID {
		t.Fatalf("id=%s", res.Abandoned[0].SessionID)
	}
}

func runAbandonIdleOK(t *testing.T, store *PostgresStore, ids mockIDs) {
	runAbandonIdleCase(t, store, ids, abandonIdleExpect{count: 1, checkID: true})
}

func runAbandonIdleSkipLock(t *testing.T, store *PostgresStore, ids mockIDs) {
	runAbandonIdleCase(t, store, ids, abandonIdleExpect{skipped: true})
}

func runAbandonIdleEmpty(t *testing.T, store *PostgresStore, ids mockIDs) {
	runAbandonIdleCase(t, store, ids, abandonIdleExpect{})
}

func runAbandonIdleErr(t *testing.T, store *PostgresStore, ids mockIDs) {
	runAbandonIdleCase(t, store, ids, abandonIdleExpect{wantErr: true})
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
	store, err := NewPostgresStore(PostgresStoreDeps{
		DB: db, Tracer: telemetry.NoopTracer("ibex-session"),
	})
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
