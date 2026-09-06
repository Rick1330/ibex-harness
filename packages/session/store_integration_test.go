//go:build integration

package session_test

import (
	"context"
	"database/sql"
	"errors"
	"os"
	"testing"
	"time"

	migratepg "github.com/Rick1330/ibex-harness/infra/migrations/postgres"
	"github.com/Rick1330/ibex-harness/packages/session"
	"github.com/Rick1330/ibex-harness/packages/telemetry"
	"github.com/google/uuid"

	// Register the lib/pq "postgres" driver for sql.Open in integration tests.
	_ "github.com/lib/pq"
)

const defaultTestDSN = "postgres://ibex:ibex@localhost:5433/ibex_test?sslmode=disable"

const seedInsertOrgSQL = `
INSERT INTO ibex_core.organizations (name, slug) VALUES ($1, $2)
RETURNING id::text`

const seedInsertUserSQL = `
INSERT INTO ibex_core.users (org_id, email, name)
VALUES ($1::uuid, $2, $3) RETURNING id::text`

const seedInsertAgentSQL = `
INSERT INTO ibex_core.agents (org_id, created_by, name, slug)
VALUES ($1::uuid, $2::uuid, $3, $4) RETURNING id::text`

const seedSetStatusSQL = `
UPDATE ibex_core.sessions SET status = $1
WHERE id = $2::uuid AND org_id = $3::uuid`

func TestStore_GetOrCreate_ExternalIDSemantics(t *testing.T) {
	cases := []struct {
		name     string
		ext      string
		wantSame bool
	}{
		{name: "idempotent", ext: "ext-idem", wantSame: true},
		{name: "empty_always_new", ext: "", wantSame: false},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			ids := setupStore(t)
			a := mustCreate(t, ids, tc.ext)
			b := mustCreate(t, ids, tc.ext)
			same := a.ID == b.ID
			if same != tc.wantSame {
				t.Fatalf("same=%v want %v (%s vs %s)", same, tc.wantSame, a.ID, b.ID)
			}
		})
	}
}

func TestStore_AppendCheckpoint_AtomicStats(t *testing.T) {
	ids := setupStore(t)
	sess := mustCreate(t, ids, "ext-stats")
	err := ids.store.AppendCheckpoint(context.Background(), session.CheckpointParams{
		SessionID: sess.ID, OrgID: ids.orgID, AgentID: ids.agentID, TurnIndex: 0,
		RequestID: "req-1", MessagesHash: "mh1", InputTokens: 10, OutputTokens: 20,
		Model: "gpt-4o", Provider: "openai", LatencyMs: 100, IsComplete: true,
	})
	if err != nil {
		t.Fatalf("append: %v", err)
	}
	assertSessionStats(t, mustReload(t, ids, "ext-stats"), sessionStatsWant{
		turns: 1, input: 10, output: 20, latency: 100,
	})
}

func TestStore_AppendCheckpoint_DuplicateTurn(t *testing.T) {
	ids := setupStore(t)
	sess := mustCreate(t, ids, "ext-dup")
	p := session.CheckpointParams{
		SessionID: sess.ID, OrgID: ids.orgID, AgentID: ids.agentID, TurnIndex: 0,
		RequestID: "req-1", MessagesHash: "mh1", Model: "gpt-4o", Provider: "openai",
		LatencyMs: 1, IsComplete: true,
	}
	if err := ids.store.AppendCheckpoint(context.Background(), p); err != nil {
		t.Fatalf("first: %v", err)
	}
	err := ids.store.AppendCheckpoint(context.Background(), p)
	if !errors.Is(err, session.ErrDuplicateTurn) {
		t.Fatalf("expected ErrDuplicateTurn, got %v", err)
	}
}

func TestStore_Complete(t *testing.T) {
	ids := setupStore(t)
	sess := mustCreate(t, ids, "ext-done")
	res, err := ids.store.Complete(context.Background(), sess.ID, ids.orgID)
	if err != nil {
		t.Fatalf("complete: %v", err)
	}
	if res != session.CompleteOK {
		t.Fatalf("result=%v want OK", res)
	}
	got := mustReload(t, ids, "ext-done")
	if got.Status != session.StatusCompleted {
		t.Fatalf("status=%s", got.Status)
	}
	res, err = ids.store.Complete(context.Background(), sess.ID, ids.orgID)
	if err != nil {
		t.Fatalf("noop complete: %v", err)
	}
	if res != session.CompleteNoop {
		t.Fatalf("result=%v want Noop", res)
	}
}

func TestStore_Complete_TerminalNoop(t *testing.T) {
	ids := setupStore(t)
	sess := mustCreate(t, ids, "ext-abandon")
	forceStatus(t, ids, sess.ID, session.StatusAbandoned)
	res, err := ids.store.Complete(context.Background(), sess.ID, ids.orgID)
	if err != nil {
		t.Fatalf("complete abandoned: %v", err)
	}
	if res != session.CompleteNoop {
		t.Fatalf("result=%v want Noop", res)
	}
	got := mustReload(t, ids, "ext-abandon")
	if got.Status != session.StatusAbandoned {
		t.Fatalf("expected abandoned preserved, got %s", got.Status)
	}
}

func TestStore_AppendCheckpoint_MissingSession(t *testing.T) {
	ids := setupStore(t)
	sess := mustCreate(t, ids, "ext-soft-del")
	softDeleteSession(t, ids, sess.ID)
	err := ids.store.AppendCheckpoint(context.Background(), session.CheckpointParams{
		SessionID: sess.ID, OrgID: ids.orgID, AgentID: ids.agentID, TurnIndex: 0,
		RequestID: "req", MessagesHash: "mh", Model: "gpt-4o", Provider: "openai",
		LatencyMs: 1, IsComplete: true,
	})
	if !errors.Is(err, session.ErrNotFound) {
		t.Fatalf("expected ErrNotFound, got %v", err)
	}
}

func TestStore_Complete_NotFound(t *testing.T) {
	ids := setupStore(t)
	res, err := ids.store.Complete(context.Background(), uuid.New(), ids.orgID)
	if err != nil {
		t.Fatalf("unexpected err: %v", err)
	}
	if res != session.CompleteNotFound {
		t.Fatalf("result=%v want NotFound", res)
	}
}

func TestStore_Complete_ConcurrentRace(t *testing.T) {
	ids := setupStore(t)
	sess := mustCreate(t, ids, "ext-complete-race")
	const workers = 8
	errs := make(chan error, workers)
	for i := 0; i < workers; i++ {
		go func() {
			_, err := ids.store.Complete(context.Background(), sess.ID, ids.orgID)
			errs <- err
		}()
	}
	for i := 0; i < workers; i++ {
		if err := <-errs; err != nil {
			t.Fatalf("worker: %v", err)
		}
	}
	got := mustReload(t, ids, "ext-complete-race")
	if got.Status != session.StatusCompleted {
		t.Fatalf("status=%s", got.Status)
	}
}

func TestStore_GetOrCreate_UniqueRaceResolvesExisting(t *testing.T) {
	ids := setupStore(t)
	ext := "ext-race-" + uuid.NewString()
	idsOut := fanoutGetOrCreate(t, ids, ext, 8)
	first := idsOut[0]
	for _, got := range idsOut[1:] {
		if got != first {
			t.Fatalf("expected single session id, got %s and %s", first, got)
		}
	}
}

type getOrCreateResult struct {
	id  uuid.UUID
	err error
}

func fanoutGetOrCreate(t *testing.T, ids storeIDs, ext string, workers int) []uuid.UUID {
	t.Helper()
	out := make(chan getOrCreateResult, workers)
	params := baseParams(ids, ext)
	for i := 0; i < workers; i++ {
		go publishGetOrCreate(ids.store, params, out)
	}
	return collectSessionIDs(t, out, workers)
}

func publishGetOrCreate(store *session.PostgresStore, params session.GetOrCreateParams, out chan<- getOrCreateResult) {
	sess, err := store.GetOrCreate(context.Background(), params)
	var id uuid.UUID
	if sess != nil {
		id = sess.ID
	}
	out <- getOrCreateResult{id: id, err: err}
}

func collectSessionIDs(t *testing.T, out <-chan getOrCreateResult, n int) []uuid.UUID {
	t.Helper()
	idsOut := make([]uuid.UUID, 0, n)
	for i := 0; i < n; i++ {
		idsOut = append(idsOut, mustSessionID(t, <-out))
	}
	return idsOut
}

func mustSessionID(t *testing.T, got getOrCreateResult) uuid.UUID {
	t.Helper()
	if got.err != nil {
		t.Fatalf("worker: %v", got.err)
	}
	return got.id
}

func TestStore_RLS_CrossOrg(t *testing.T) {
	db, store := openStore(t)
	orgA, agentA := seedOrgAgent(t, db, "Org A", "org-a")
	orgB, _ := seedOrgAgent(t, db, "Org B", "org-b")
	ids := storeIDs{db: db, store: store, orgID: orgA, agentID: agentA}
	sess := mustCreate(t, ids, "ext-rls")

	err := store.AppendCheckpoint(context.Background(), session.CheckpointParams{
		SessionID: sess.ID, OrgID: orgB, AgentID: agentA, TurnIndex: 0,
		RequestID: "x", MessagesHash: "h", Model: "gpt-4o", Provider: "openai",
		LatencyMs: 1, IsComplete: true,
	})
	if err == nil {
		t.Fatal("expected cross-org append to fail")
	}
	res, err := store.Complete(context.Background(), sess.ID, orgB)
	if err != nil {
		t.Fatalf("unexpected err: %v", err)
	}
	if res != session.CompleteNotFound {
		t.Fatalf("expected CompleteNotFound, got %v", res)
	}
}

func TestStore_CompleteByExternalID(t *testing.T) {
	ids := setupStore(t)
	sess := mustCreate(t, ids, "ext-by-ext")
	res, gotID, err := ids.store.CompleteByExternalID(context.Background(), ids.orgID, ids.agentID, "ext-by-ext")
	if err != nil {
		t.Fatalf("complete: %v", err)
	}
	if res != session.CompleteOK || gotID != sess.ID {
		t.Fatalf("res=%v id=%s want OK/%s", res, gotID, sess.ID)
	}
	res, gotID, err = ids.store.CompleteByExternalID(context.Background(), ids.orgID, ids.agentID, "ext-by-ext")
	if err != nil {
		t.Fatalf("noop: %v", err)
	}
	if res != session.CompleteNoop || gotID != sess.ID {
		t.Fatalf("res=%v id=%s want Noop/%s", res, gotID, sess.ID)
	}
}

func TestStore_CompleteByExternalID_NotFoundAndEmpty(t *testing.T) {
	ids := setupStore(t)
	res, id, err := ids.store.CompleteByExternalID(context.Background(), ids.orgID, ids.agentID, "missing")
	if err != nil || res != session.CompleteNotFound || id != uuid.Nil {
		t.Fatalf("missing: res=%v id=%s err=%v", res, id, err)
	}
	res, id, err = ids.store.CompleteByExternalID(context.Background(), ids.orgID, ids.agentID, "")
	if err != nil || res != session.CompleteNotFound || id != uuid.Nil {
		t.Fatalf("empty: res=%v id=%s err=%v", res, id, err)
	}
}

func TestStore_CompleteByExternalID_CrossAgentIsolation(t *testing.T) {
	db, store := openStore(t)
	orgID, agentA := seedOrgAgent(t, db, "Org Iso", "org-iso-"+uuid.NewString()[:8])
	_, agentB := seedOrgAgentSameOrg(t, db, orgID, "agent-b-"+uuid.NewString()[:8])
	idsA := storeIDs{db: db, store: store, orgID: orgID, agentID: agentA}
	mustCreate(t, idsA, "shared-ext")
	res, _, err := store.CompleteByExternalID(context.Background(), orgID, agentB, "shared-ext")
	if err != nil {
		t.Fatalf("err: %v", err)
	}
	if res != session.CompleteNotFound {
		t.Fatalf("agent B must not see agent A session, got %v", res)
	}
	got := mustReload(t, idsA, "shared-ext")
	if got.Status != session.StatusActive {
		t.Fatalf("status=%s want active", got.Status)
	}
}

type storeIDs struct {
	db             *sql.DB
	store          *session.PostgresStore
	orgID, agentID uuid.UUID
}

type sessionStatsWant struct {
	turns                  int
	input, output, latency int64
}

func setupStore(t *testing.T) storeIDs {
	t.Helper()
	db, store := openStore(t)
	orgID, agentID := seedOrgAgent(t, db, "Org S", "org-s-"+uuid.NewString()[:8])
	return storeIDs{db: db, store: store, orgID: orgID, agentID: agentID}
}

func openStore(t *testing.T) (*sql.DB, *session.PostgresStore) {
	t.Helper()
	dsn := integrationDSN()
	db, err := sql.Open("postgres", dsn)
	if err != nil {
		t.Fatalf("open: %v", err)
	}
	t.Cleanup(func() { _ = db.Close() })
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := db.PingContext(ctx); err != nil {
		t.Skipf("postgres not available: %v", err)
	}
	resetSchema(t, db)
	if err := migratepg.Up(dsn); err != nil {
		t.Fatalf("migrate: %v", err)
	}
	store, err := session.NewPostgresStore(session.PostgresStoreDeps{
		DB: db, Tracer: telemetry.NoopTracer("ibex-session"),
	})
	if err != nil {
		t.Fatalf("store: %v", err)
	}
	return db, store
}

func integrationDSN() string {
	if dsn := os.Getenv("POSTGRES_TEST_DSN"); dsn != "" {
		return dsn
	}
	return defaultTestDSN
}

func resetSchema(t *testing.T, db *sql.DB) {
	t.Helper()
	ctx := context.Background()
	_, _ = db.ExecContext(ctx, `DROP SCHEMA IF EXISTS ibex_core CASCADE`)
	_, _ = db.ExecContext(ctx, `DROP TABLE IF EXISTS schema_migrations`)
	_, _ = db.ExecContext(ctx, `DROP ROLE IF EXISTS ibex_app`)
}

func seedOrgAgent(t *testing.T, db *sql.DB, name, slug string) (uuid.UUID, uuid.UUID) {
	t.Helper()
	ctx := context.Background()
	email := slug + "@example.com"
	agentName := name + " Agent"
	agentSlug := "agent-" + slug
	var orgID, userID, agentID string
	err := withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		if err := tx.QueryRowContext(ctx, seedInsertOrgSQL, name, slug).Scan(&orgID); err != nil {
			return err
		}
		if err := tx.QueryRowContext(ctx, seedInsertUserSQL, orgID, email, name).Scan(&userID); err != nil {
			return err
		}
		return tx.QueryRowContext(ctx, seedInsertAgentSQL, orgID, userID, agentName, agentSlug).Scan(&agentID)
	})
	if err != nil {
		t.Fatalf("seed: %v", err)
	}
	return uuid.MustParse(orgID), uuid.MustParse(agentID)
}

func seedOrgAgentSameOrg(t *testing.T, db *sql.DB, orgID uuid.UUID, agentSlug string) (uuid.UUID, uuid.UUID) {
	t.Helper()
	ctx := context.Background()
	email := agentSlug + "@example.com"
	agentName := "Agent " + agentSlug
	var userID, agentID string
	err := withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		if err := tx.QueryRowContext(ctx, seedInsertUserSQL, orgID.String(), email, agentName).Scan(&userID); err != nil {
			return err
		}
		return tx.QueryRowContext(ctx, seedInsertAgentSQL, orgID.String(), userID, agentName, agentSlug).Scan(&agentID)
	})
	if err != nil {
		t.Fatalf("seed agent: %v", err)
	}
	return orgID, uuid.MustParse(agentID)
}

func withServiceAccount(ctx context.Context, db *sql.DB, fn func(*sql.Tx) error) error {
	tx, err := db.BeginTx(ctx, nil)
	if err != nil {
		return err
	}
	defer func() { _ = tx.Rollback() }()
	if _, err := tx.ExecContext(ctx, `SELECT set_config('app.is_service_account', 'true', true)`); err != nil {
		return err
	}
	if err := fn(tx); err != nil {
		return err
	}
	return tx.Commit()
}

func baseParams(ids storeIDs, ext string) session.GetOrCreateParams {
	return session.GetOrCreateParams{
		OrgID: ids.orgID, AgentID: ids.agentID, ExternalID: ext,
		Model: "gpt-4o", Provider: "openai",
	}
}

func mustCreate(t *testing.T, ids storeIDs, ext string) *session.Session {
	t.Helper()
	sess, err := ids.store.GetOrCreate(context.Background(), baseParams(ids, ext))
	if err != nil {
		t.Fatalf("create: %v", err)
	}
	return sess
}

func mustReload(t *testing.T, ids storeIDs, ext string) *session.Session {
	t.Helper()
	sess, err := ids.store.GetOrCreate(context.Background(), baseParams(ids, ext))
	if err != nil {
		t.Fatalf("reload: %v", err)
	}
	return sess
}

func assertSessionStats(t *testing.T, got *session.Session, want sessionStatsWant) {
	t.Helper()
	if got.TurnCount != want.turns {
		t.Fatalf("turn_count=%d want %d", got.TurnCount, want.turns)
	}
	if got.TotalInputTokens != want.input {
		t.Fatalf("input_tokens=%d want %d", got.TotalInputTokens, want.input)
	}
	if got.TotalOutputTokens != want.output {
		t.Fatalf("output_tokens=%d want %d", got.TotalOutputTokens, want.output)
	}
	if got.TotalLatencyMs != want.latency {
		t.Fatalf("latency_ms=%d want %d", got.TotalLatencyMs, want.latency)
	}
}

func forceStatus(t *testing.T, ids storeIDs, sessionID uuid.UUID, status string) {
	t.Helper()
	ctx := context.Background()
	err := withServiceAccount(ctx, ids.db, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(ctx, seedSetStatusSQL, status, sessionID, ids.orgID)
		return err
	})
	if err != nil {
		t.Fatalf("force status: %v", err)
	}
}

const softDeleteSessionSQL = `
UPDATE ibex_core.sessions SET deleted_at = NOW()
WHERE id = $1::uuid AND org_id = $2::uuid`

func softDeleteSession(t *testing.T, ids storeIDs, sessionID uuid.UUID) {
	t.Helper()
	ctx := context.Background()
	err := withServiceAccount(ctx, ids.db, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(ctx, softDeleteSessionSQL, sessionID, ids.orgID)
		return err
	})
	if err != nil {
		t.Fatalf("soft delete: %v", err)
	}
}
