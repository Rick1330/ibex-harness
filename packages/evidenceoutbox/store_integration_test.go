//go:build integration

package evidenceoutbox_test

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"os"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	migratepg "github.com/Rick1330/ibex-harness/infra/migrations/postgres"
	"github.com/Rick1330/ibex-harness/packages/evidenceoutbox"
	"github.com/google/uuid"

	_ "github.com/lib/pq" // PostgreSQL driver for integration PersistRun/relay tests
)

const defaultTestDSN = "postgres://ibex:ibex@localhost:5433/ibex_test?sslmode=disable"

func openTestDB(t *testing.T) *sql.DB {
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
	return db
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

func seedOrg(t *testing.T, db *sql.DB) uuid.UUID {
	t.Helper()
	var id uuid.UUID
	const q = `INSERT INTO ibex_core.organizations (name, slug) VALUES ($1, $2) RETURNING id`
	err := db.QueryRowContext(context.Background(), q, "evidence-test", uuid.NewString()).Scan(&id)
	if err != nil {
		t.Fatalf("seed org: %v", err)
	}
	return id
}

func seedSession(t *testing.T, db *sql.DB, orgID uuid.UUID) uuid.UUID {
	t.Helper()
	ctx := context.Background()
	tx, err := db.BeginTx(ctx, nil)
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = tx.Rollback() }()
	// users/agents/sessions still use platform rls_org_visible (GUC), not evidence role.
	const setRLS = `SELECT set_config('app.is_service_account', 'true', true)`
	_, _ = tx.ExecContext(ctx, setRLS)

	var userID, agentID, sessionID uuid.UUID
	const insertUser = `
INSERT INTO ibex_core.users (org_id, email, name)
VALUES ($1, $2, $3) RETURNING id`
	if err := tx.QueryRowContext(ctx, insertUser, orgID, uuid.NewString()+"@ex.com", "u").Scan(&userID); err != nil {
		t.Fatalf("user: %v", err)
	}
	const insertAgent = `
INSERT INTO ibex_core.agents (org_id, created_by, name, slug)
VALUES ($1, $2, $3, $4) RETURNING id`
	if err := tx.QueryRowContext(ctx, insertAgent, orgID, userID, "a", uuid.NewString()[:8]).Scan(&agentID); err != nil {
		t.Fatalf("agent: %v", err)
	}
	const insertSession = `
INSERT INTO ibex_core.sessions (org_id, agent_id, model, provider)
VALUES ($1, $2, 'm', 'p') RETURNING id`
	if err := tx.QueryRowContext(ctx, insertSession, orgID, agentID).Scan(&sessionID); err != nil {
		t.Fatalf("session: %v", err)
	}
	if err := tx.Commit(); err != nil {
		t.Fatal(err)
	}
	return sessionID
}

type recordingDeliverer struct {
	mu    sync.Mutex
	seen  map[string]int
	failN atomic.Int32
}

func (s *recordingDeliverer) Deliver(_ context.Context, row evidenceoutbox.OutboxRow) error {
	if s.failN.Add(-1) >= 0 {
		return errors.New("injected deliverer failure")
	}
	key := row.EventID.String() + ":" + fmt.Sprintf("%d", row.AggregateSeq)
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.seen == nil {
		s.seen = map[string]int{}
	}
	s.seen[key]++
	return nil
}

func (s *recordingDeliverer) count() int {
	s.mu.Lock()
	defer s.mu.Unlock()
	n := 0
	for _, c := range s.seen {
		n += c
	}
	return n
}

func (s *recordingDeliverer) unique() int {
	s.mu.Lock()
	defer s.mu.Unlock()
	return len(s.seen)
}

func TestIntegration_PersistRun_WritesEvidenceAndOutbox(t *testing.T) {
	db := openTestDB(t)
	defer func() { _ = db.Close() }()
	orgID := seedOrg(t, db)
	sessionID := seedSession(t, db, orgID)

	store, err := evidenceoutbox.NewStore(db)
	if err != nil {
		t.Fatal(err)
	}
	res, err := store.PersistRun(context.Background(), fullPersistRunInput(orgID, sessionID))
	if err != nil {
		t.Fatalf("PersistRun: %v", err)
	}
	if res.RunID == uuid.Nil {
		t.Fatal("empty run id")
	}
	if len(res.OutboxIDs) < 5 {
		t.Fatalf("outbox rows=%d want >=5", len(res.OutboxIDs))
	}

	assertPersistRunMetrics(t, db, res.RunID, 12)
}

func fullPersistRunInput(orgID, sessionID uuid.UUID) evidenceoutbox.RunInput {
	agent := uuid.New()
	mem := uuid.New()
	rank := 1
	sim := 0.9
	comp := 0.85
	return evidenceoutbox.RunInput{
		OrgID:      orgID,
		AgentID:    &agent,
		SessionID:  &sessionID,
		RequestID:  "req-" + uuid.NewString(),
		TraceID:    strings.ReplaceAll(uuid.NewString(), "-", ""),
		RootSpanID: "span-root",
		Spans: []evidenceoutbox.SpanInput{
			{SpanID: "span-root", OperationKind: "proxy.chat", Status: "ok"},
			{SpanID: "span-assemble", ParentSpanID: "span-root", OperationKind: "context.assemble", Status: "ok"},
		},
		Metrics: &evidenceoutbox.AssemblyMetrics{TotalMs: 12, RankingMs: 3, CandidatesEvaluated: 2},
		Candidates: []evidenceoutbox.ScoreCandidate{
			{
				MemoryID: mem, RetrievalRank: 1, FinalRank: &rank,
				Similarity: &sim, CompositeScore: &comp,
				ScoreSchema:     evidenceoutbox.ScoreSchemaInterim,
				ScoreComponents: map[string]float64{"similarity": 0.85, "confidence": 0.15},
				Exclusion:       "included",
			},
		},
		Directive: &evidenceoutbox.DirectiveSnapshot{ContentHash: "abc"},
		Tools: []evidenceoutbox.ToolAudit{
			{ToolName: "search", IdempotencyKey: "ik-1", SanitizedArgs: map[string]any{"q": "x"}},
		},
		SessionEvents: []evidenceoutbox.SessionEventInput{
			{SessionID: sessionID, SequenceNumber: 1, EventType: "evidence_assembly", Data: map[string]any{"ok": true}},
		},
	}
}

func assertPersistRunMetrics(t *testing.T, db *sql.DB, runID uuid.UUID, wantTotal int) {
	t.Helper()
	tx := beginServiceTx(t, db)
	var metricsTotal int
	const q = `SELECT total_ms FROM ibex_core.evidence_assembly_metrics WHERE run_id = $1`
	if err := tx.QueryRowContext(context.Background(), q, runID).Scan(&metricsTotal); err != nil {
		t.Fatalf("metrics: %v", err)
	}
	if err := tx.Commit(); err != nil {
		t.Fatalf("commit metrics tx: %v", err)
	}
	if metricsTotal != wantTotal {
		t.Fatalf("total_ms=%d want %d", metricsTotal, wantTotal)
	}
}

func TestIntegration_OutboxCrashReplay_NoLostOrDupDeliveredSemantics(t *testing.T) {
	db := openTestDB(t)
	defer func() { _ = db.Close() }()
	orgID := seedOrg(t, db)
	store := mustStore(t, db)
	traceID := strings.ReplaceAll(uuid.NewString(), "-", "")
	requestID := persistMinimalRun(t, store, orgID, traceID)

	deliverer := &recordingDeliverer{}
	relay := mustRelay(t, db, deliverer)
	forceStaleInFlight(t, db, orgID, requestID)
	assertRecoveredAndDeliveredOnce(t, relay, deliverer)
}

func assertRecoveredAndDeliveredOnce(t *testing.T, relay *evidenceoutbox.Relay, d *recordingDeliverer) {
	t.Helper()
	n, err := relay.RecoverInFlight(context.Background(), time.Nanosecond)
	if err != nil {
		t.Fatalf("recover: %v", err)
	}
	if n == 0 {
		t.Fatal("expected recovered in_flight rows")
	}
	res, err := relay.ProcessBatch(context.Background())
	if err != nil {
		t.Fatalf("process: %v", err)
	}
	if res.Delivered == 0 {
		t.Fatalf("delivered=0 claimed=%d", res.Claimed)
	}
	res2, err := relay.ProcessBatch(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if res2.Claimed != 0 {
		t.Fatalf("second claim=%d want 0 (no duplicate delivery)", res2.Claimed)
	}
	if d.unique() != d.count() {
		t.Fatalf("duplicate deliveries: unique=%d count=%d", d.unique(), d.count())
	}
}

func mustStore(t *testing.T, db *sql.DB) *evidenceoutbox.Store {
	t.Helper()
	store, err := evidenceoutbox.NewStore(db)
	if err != nil {
		t.Fatal(err)
	}
	return store
}

func mustRelay(t *testing.T, db *sql.DB, sink evidenceoutbox.Deliverer) *evidenceoutbox.Relay {
	t.Helper()
	relay, err := evidenceoutbox.NewRelay(db, sink, evidenceoutbox.RelayConfig{BatchSize: 10, MaxAttempts: 5})
	if err != nil {
		t.Fatal(err)
	}
	return relay
}

func persistMinimalRun(t *testing.T, store *evidenceoutbox.Store, orgID uuid.UUID, traceID string) string {
	t.Helper()
	requestID := "req-crash-" + uuid.NewString()
	_, err := store.PersistRun(context.Background(), evidenceoutbox.RunInput{
		OrgID:     orgID,
		RequestID: requestID,
		TraceID:   traceID,
		Spans:     []evidenceoutbox.SpanInput{{SpanID: "s1", OperationKind: "proxy.chat"}},
		Metrics:   &evidenceoutbox.AssemblyMetrics{TotalMs: 1},
	})
	if err != nil {
		t.Fatalf("persist: %v", err)
	}
	return requestID
}

func forceStaleInFlight(t *testing.T, db *sql.DB, orgID uuid.UUID, aggregateID string) {
	t.Helper()
	// Test DSN is superuser (bypasses FORCE RLS). Production relay uses
	// SECURITY DEFINER helpers owned by ibex_service — never SET ROLE from ibex_app.
	tx, err := db.Begin()
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = tx.Rollback() }()
	const q = `
UPDATE ibex_core.evidence_outbox
SET delivery_status = 'in_flight', attempts = attempts + 1, claimed_at = NOW() - interval '1 minute'
WHERE org_id = $1 AND aggregate_id = $2 AND delivery_status = 'pending'`
	if _, err = tx.ExecContext(context.Background(), q, orgID, aggregateID); err != nil {
		t.Fatal(err)
	}
	if err := tx.Commit(); err != nil {
		t.Fatal(err)
	}
}

func TestIntegration_GoldenNestedRun_JoinKeys(t *testing.T) {
	db := openTestDB(t)
	defer func() { _ = db.Close() }()
	orgID := seedOrg(t, db)
	sessionID := seedSession(t, db, orgID)
	store := mustStore(t, db)

	keys := goldenJoinKeys{
		TraceID:    "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
		RequestID:  "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
		Checkpoint: uuid.MustParse("cccccccc-cccc-cccc-cccc-cccccccccccc"),
		Root:       "1111111111111111",
		Child:      "2222222222222222",
	}

	res, err := store.PersistRun(context.Background(), goldenRunInput(orgID, sessionID, keys))
	if err != nil {
		t.Fatalf("golden persist: %v", err)
	}
	assertGoldenJoins(t, goldenAssert{db: db, res: res, orgID: orgID, keys: keys})
}

func goldenRunInput(orgID, sessionID uuid.UUID, keys goldenJoinKeys) evidenceoutbox.RunInput {
	return evidenceoutbox.RunInput{
		OrgID:        orgID,
		SessionID:    &sessionID,
		RequestID:    keys.RequestID,
		TraceID:      keys.TraceID,
		RootSpanID:   keys.Root,
		CheckpointID: &keys.Checkpoint,
		Completeness: "complete",
		Spans: []evidenceoutbox.SpanInput{
			{SpanID: keys.Root, OperationKind: "proxy.chat", Status: "ok"},
			{SpanID: keys.Child, ParentSpanID: keys.Root, OperationKind: "context.assemble", Status: "ok"},
			{SpanID: "3333333333333333", ParentSpanID: keys.Root, OperationKind: "provider.complete", Status: "ok"},
			{SpanID: "4444444444444444", ParentSpanID: keys.Root, OperationKind: "tool.search", Status: "ok"},
		},
		Metrics: &evidenceoutbox.AssemblyMetrics{
			BudgetCalculationMs: 1, RankingMs: 2, PackingMs: 3, TotalMs: 10, CandidatesEvaluated: 3,
		},
		Candidates: []evidenceoutbox.ScoreCandidate{
			{MemoryID: uuid.New(), RetrievalRank: 1, Exclusion: "included", ScoreSchema: evidenceoutbox.ScoreSchemaInterim},
			{MemoryID: uuid.New(), RetrievalRank: 2, Exclusion: "budget", ScoreSchema: evidenceoutbox.ScoreSchemaInterim},
		},
		Directive: &evidenceoutbox.DirectiveSnapshot{ContentHash: "golden-hash"},
		Tools: []evidenceoutbox.ToolAudit{
			{SpanID: "4444444444444444", ToolName: "search", IdempotencyKey: "gold-1", SanitizedArgs: map[string]any{"q": "nested"}},
		},
		SessionEvents: []evidenceoutbox.SessionEventInput{
			{SessionID: sessionID, SequenceNumber: 1, EventType: "inference_request", Data: map[string]any{"model": "m"}},
			{SessionID: sessionID, SequenceNumber: 2, EventType: "evidence_span", Data: map[string]any{"span": keys.Child}},
		},
	}
}

func assertGoldenJoins(t *testing.T, a goldenAssert) {
	t.Helper()
	tx := beginServiceTx(t, a.db)
	assertGoldenSpanCount(t, tx, a.orgID, a.keys)
	assertGoldenParent(t, tx, a.orgID, a.keys)
	assertGoldenCheckpoint(t, tx, a.res.RunID, a.keys.Checkpoint)
	assertGoldenOutboxPending(t, tx, a.orgID, a.keys.RequestID)
	_ = tx.Commit()
	t.Logf("golden nested-run ok run_id=%s", a.res.RunID)
}

type goldenAssert struct {
	db    *sql.DB
	res   evidenceoutbox.PersistResult
	orgID uuid.UUID
	keys  goldenJoinKeys
}

type goldenJoinKeys struct {
	TraceID    string
	RequestID  string
	Checkpoint uuid.UUID
	Root       string
	Child      string
}

func beginServiceTx(t *testing.T, db *sql.DB) *sql.Tx {
	t.Helper()
	// Superuser test DSN bypasses FORCE RLS for cross-row asserts.
	tx, err := db.Begin()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = tx.Rollback() })
	return tx
}

func assertGoldenSpanCount(t *testing.T, tx *sql.Tx, orgID uuid.UUID, keys goldenJoinKeys) {
	t.Helper()
	var spanCount int
	const q = `
SELECT COUNT(*) FROM ibex_core.evidence_spans
WHERE org_id = $1 AND trace_id = $2 AND request_id = $3`
	if err := tx.QueryRowContext(context.Background(), q, orgID, keys.TraceID, keys.RequestID).Scan(&spanCount); err != nil {
		t.Fatal(err)
	}
	if spanCount != 4 {
		t.Fatalf("spans=%d want 4", spanCount)
	}
}

func assertGoldenParent(t *testing.T, tx *sql.Tx, orgID uuid.UUID, keys goldenJoinKeys) {
	t.Helper()
	var parent string
	const q = `
SELECT parent_span_id FROM ibex_core.evidence_spans
WHERE org_id = $1 AND span_id = $2`
	if err := tx.QueryRowContext(context.Background(), q, orgID, keys.Child).Scan(&parent); err != nil {
		t.Fatal(err)
	}
	if parent != keys.Root {
		t.Fatalf("parent=%q want %q", parent, keys.Root)
	}
}

func assertGoldenCheckpoint(t *testing.T, tx *sql.Tx, runID, checkpoint uuid.UUID) {
	t.Helper()
	var ck uuid.UUID
	const q = `SELECT checkpoint_id FROM ibex_core.evidence_runs WHERE id = $1`
	if err := tx.QueryRowContext(context.Background(), q, runID).Scan(&ck); err != nil {
		t.Fatal(err)
	}
	if ck != checkpoint {
		t.Fatalf("checkpoint=%s", ck)
	}
}

func assertGoldenOutboxPending(t *testing.T, tx *sql.Tx, orgID uuid.UUID, aggregateID string) {
	t.Helper()
	var outboxPending int
	const q = `
SELECT COUNT(*) FROM ibex_core.evidence_outbox
WHERE org_id = $1 AND aggregate_id = $2 AND delivery_status = 'pending'`
	if err := tx.QueryRowContext(context.Background(), q, orgID, aggregateID).Scan(&outboxPending); err != nil {
		t.Fatal(err)
	}
	if outboxPending < 6 {
		t.Fatalf("pending outbox=%d", outboxPending)
	}
}
