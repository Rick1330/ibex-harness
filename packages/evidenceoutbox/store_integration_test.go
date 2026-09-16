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

	_ "github.com/lib/pq"
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
	slug := "ev-" + uuid.NewString()[:8]
	err := db.QueryRow(`
INSERT INTO ibex_core.organizations (name, slug) VALUES ($1, $2) RETURNING id`,
		"evidence-test", slug).Scan(&id)
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
	_, _ = tx.ExecContext(ctx, `SELECT set_config('app.is_service_account', 'true', true)`)

	var userID, agentID, sessionID uuid.UUID
	if err := tx.QueryRowContext(ctx, `
INSERT INTO ibex_core.users (org_id, email, name)
VALUES ($1, $2, $3) RETURNING id`, orgID, uuid.NewString()+"@ex.com", "u").Scan(&userID); err != nil {
		t.Fatalf("user: %v", err)
	}
	if err := tx.QueryRowContext(ctx, `
INSERT INTO ibex_core.agents (org_id, created_by, name, slug)
VALUES ($1, $2, $3, $4) RETURNING id`, orgID, userID, "a", uuid.NewString()[:8]).Scan(&agentID); err != nil {
		t.Fatalf("agent: %v", err)
	}
	if err := tx.QueryRowContext(ctx, `
INSERT INTO ibex_core.sessions (org_id, agent_id, model, provider)
VALUES ($1, $2, 'm', 'p') RETURNING id`, orgID, agentID).Scan(&sessionID); err != nil {
		t.Fatalf("session: %v", err)
	}
	if err := tx.Commit(); err != nil {
		t.Fatal(err)
	}
	return sessionID
}

type recordingSink struct {
	mu    sync.Mutex
	seen  map[string]int
	failN atomic.Int32
}

func (s *recordingSink) Deliver(_ context.Context, row evidenceoutbox.OutboxRow) error {
	if s.failN.Add(-1) >= 0 {
		return errors.New("injected sink failure")
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

func (s *recordingSink) count() int {
	s.mu.Lock()
	defer s.mu.Unlock()
	n := 0
	for _, c := range s.seen {
		n += c
	}
	return n
}

func (s *recordingSink) unique() int {
	s.mu.Lock()
	defer s.mu.Unlock()
	return len(s.seen)
}

func TestIntegration_PersistRun_WritesEvidenceAndOutbox(t *testing.T) {
	db := openTestDB(t)
	defer db.Close()
	orgID := seedOrg(t, db)
	sessionID := seedSession(t, db, orgID)

	store, err := evidenceoutbox.NewStore(db)
	if err != nil {
		t.Fatal(err)
	}
	agent := uuid.New()
	mem := uuid.New()
	rank := 1
	sim := 0.9
	comp := 0.85
	res, err := store.PersistRun(context.Background(), evidenceoutbox.RunInput{
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
	})
	if err != nil {
		t.Fatalf("PersistRun: %v", err)
	}
	if res.RunID == uuid.Nil {
		t.Fatal("empty run id")
	}
	if len(res.OutboxIDs) < 5 {
		t.Fatalf("outbox rows=%d want >=5", len(res.OutboxIDs))
	}

	var metricsTotal int
	tx, err := db.Begin()
	if err != nil {
		t.Fatalf("begin metrics tx: %v", err)
	}
	defer func() { _ = tx.Rollback() }()
	if _, err := tx.Exec(`SELECT set_config('app.is_service_account', 'true', true)`); err != nil {
		t.Fatalf("rls: %v", err)
	}
	if err := tx.QueryRow(
		`SELECT total_ms FROM ibex_core.evidence_assembly_metrics WHERE run_id = $1`,
		res.RunID,
	).Scan(&metricsTotal); err != nil {
		t.Fatalf("metrics: %v", err)
	}
	if err := tx.Commit(); err != nil {
		t.Fatalf("commit metrics tx: %v", err)
	}
	if metricsTotal != 12 {
		t.Fatalf("total_ms=%d", metricsTotal)
	}
}

func TestIntegration_OutboxCrashReplay_NoLostOrDupDeliveredSemantics(t *testing.T) {
	db := openTestDB(t)
	defer db.Close()
	orgID := seedOrg(t, db)
	store := mustStore(t, db)
	traceID := strings.ReplaceAll(uuid.NewString(), "-", "")
	persistMinimalRun(t, store, orgID, traceID)

	sink := &recordingSink{}
	relay := mustRelay(t, db, sink)
	forceStaleInFlight(t, db, orgID, traceID)

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
	if sink.unique() != sink.count() {
		t.Fatalf("duplicate sink deliveries: unique=%d count=%d", sink.unique(), sink.count())
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

func mustRelay(t *testing.T, db *sql.DB, sink evidenceoutbox.Sink) *evidenceoutbox.Relay {
	t.Helper()
	relay, err := evidenceoutbox.NewRelay(db, sink, evidenceoutbox.RelayConfig{BatchSize: 10, MaxAttempts: 5})
	if err != nil {
		t.Fatal(err)
	}
	return relay
}

func persistMinimalRun(t *testing.T, store *evidenceoutbox.Store, orgID uuid.UUID, traceID string) {
	t.Helper()
	_, err := store.PersistRun(context.Background(), evidenceoutbox.RunInput{
		OrgID:     orgID,
		RequestID: "req-crash-" + uuid.NewString(),
		TraceID:   traceID,
		Spans:     []evidenceoutbox.SpanInput{{SpanID: "s1", OperationKind: "proxy.chat"}},
		Metrics:   &evidenceoutbox.AssemblyMetrics{TotalMs: 1},
	})
	if err != nil {
		t.Fatalf("persist: %v", err)
	}
}

func forceStaleInFlight(t *testing.T, db *sql.DB, orgID uuid.UUID, traceID string) {
	t.Helper()
	tx, err := db.Begin()
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = tx.Rollback() }()
	if _, err := tx.Exec(`SELECT set_config('app.is_service_account', 'true', true)`); err != nil {
		t.Fatal(err)
	}
	_, err = tx.Exec(`
UPDATE ibex_core.evidence_outbox
SET delivery_status = 'in_flight', attempts = attempts + 1, claimed_at = NOW() - interval '1 minute'
WHERE org_id = $1 AND aggregate_id = $2 AND delivery_status = 'pending'`, orgID, traceID)
	if err != nil {
		t.Fatal(err)
	}
	if err := tx.Commit(); err != nil {
		t.Fatal(err)
	}
}

func TestIntegration_GoldenNestedRun_JoinKeys(t *testing.T) {
	db := openTestDB(t)
	defer db.Close()
	orgID := seedOrg(t, db)
	sessionID := seedSession(t, db, orgID)
	store := mustStore(t, db)

	traceID := "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
	requestID := "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
	checkpoint := uuid.MustParse("cccccccc-cccc-cccc-cccc-cccccccccccc")
	root := "1111111111111111"
	child := "2222222222222222"

	res, err := store.PersistRun(context.Background(), goldenRunInput(orgID, sessionID, traceID, requestID, checkpoint, root, child))
	if err != nil {
		t.Fatalf("golden persist: %v", err)
	}
	assertGoldenJoins(t, db, res.RunID, orgID, traceID, requestID, checkpoint, root, child)
}

func goldenRunInput(
	orgID, sessionID uuid.UUID,
	traceID, requestID string,
	checkpoint uuid.UUID,
	root, child string,
) evidenceoutbox.RunInput {
	return evidenceoutbox.RunInput{
		OrgID:        orgID,
		SessionID:    &sessionID,
		RequestID:    requestID,
		TraceID:      traceID,
		RootSpanID:   root,
		CheckpointID: &checkpoint,
		Completeness: "complete",
		Spans: []evidenceoutbox.SpanInput{
			{SpanID: root, OperationKind: "proxy.chat", Status: "ok"},
			{SpanID: child, ParentSpanID: root, OperationKind: "context.assemble", Status: "ok"},
			{SpanID: "3333333333333333", ParentSpanID: root, OperationKind: "provider.complete", Status: "ok"},
			{SpanID: "4444444444444444", ParentSpanID: root, OperationKind: "tool.search", Status: "ok"},
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
			{SessionID: sessionID, SequenceNumber: 2, EventType: "evidence_span", Data: map[string]any{"span": child}},
		},
	}
}

func assertGoldenJoins(
	t *testing.T,
	db *sql.DB,
	runID, orgID uuid.UUID,
	traceID, requestID string,
	checkpoint uuid.UUID,
	root, child string,
) {
	t.Helper()
	tx, err := db.Begin()
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = tx.Rollback() }()
	_, _ = tx.Exec(`SELECT set_config('app.is_service_account', 'true', true)`)

	var spanCount int
	if err := tx.QueryRow(`
SELECT COUNT(*) FROM ibex_core.evidence_spans
WHERE org_id = $1 AND trace_id = $2 AND request_id = $3`, orgID, traceID, requestID).Scan(&spanCount); err != nil {
		t.Fatal(err)
	}
	if spanCount != 4 {
		t.Fatalf("spans=%d want 4", spanCount)
	}

	var parent string
	if err := tx.QueryRow(`
SELECT parent_span_id FROM ibex_core.evidence_spans
WHERE org_id = $1 AND span_id = $2`, orgID, child).Scan(&parent); err != nil {
		t.Fatal(err)
	}
	if parent != root {
		t.Fatalf("parent=%q want %q", parent, root)
	}

	var ck uuid.UUID
	if err := tx.QueryRow(`
SELECT checkpoint_id FROM ibex_core.evidence_runs WHERE id = $1`, runID).Scan(&ck); err != nil {
		t.Fatal(err)
	}
	if ck != checkpoint {
		t.Fatalf("checkpoint=%s", ck)
	}

	var outboxPending int
	if err := tx.QueryRow(`
SELECT COUNT(*) FROM ibex_core.evidence_outbox
WHERE org_id = $1 AND aggregate_id = $2 AND delivery_status = 'pending'`, orgID, traceID).Scan(&outboxPending); err != nil {
		t.Fatal(err)
	}
	if outboxPending < 6 {
		t.Fatalf("pending outbox=%d", outboxPending)
	}
	_ = tx.Commit()
	t.Logf("golden nested-run ok run_id=%s outbox_pending=%d spans=%d", runID, outboxPending, spanCount)
}
