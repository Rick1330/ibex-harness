//go:build integration

package bootstrap

import (
	"context"
	"database/sql"
	"errors"
	"os"
	"strings"
	"sync"
	"testing"
	"time"

	migratepg "github.com/Rick1330/ibex-harness/infra/migrations/postgres"
	"github.com/Rick1330/ibex-harness/packages/evidenceoutbox"
	ibexmetrics "github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/services/relay/internal/fence"
	"github.com/google/uuid"
	"github.com/lib/pq"
)

const integrationDefaultDSN = "postgres://ibex:ibex@localhost:5433/ibex_test?sslmode=disable"

func integrationDSN() string {
	if dsn := os.Getenv("POSTGRES_TEST_DSN"); dsn != "" {
		return dsn
	}
	return integrationDefaultDSN
}

func openMigratedDB(t *testing.T) *sql.DB {
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
	resetIntegrationSchema(t, db)
	if err := migratepg.Up(dsn); err != nil {
		t.Fatalf("migrate: %v", err)
	}
	return db
}

func resetIntegrationSchema(t *testing.T, db *sql.DB) {
	t.Helper()
	ctx := context.Background()
	_, _ = db.ExecContext(ctx, `DROP SCHEMA IF EXISTS ibex_billing CASCADE`)
	_, _ = db.ExecContext(ctx, `DROP SCHEMA IF EXISTS ibex_core CASCADE`)
	_, _ = db.ExecContext(ctx, `DROP TABLE IF EXISTS schema_migrations`)
	_, _ = db.ExecContext(ctx, `DROP ROLE IF EXISTS ibex_app`)
	_, _ = db.ExecContext(ctx, `DROP ROLE IF EXISTS ibex_evidence_relay`)
	_, _ = db.ExecContext(ctx, `DROP ROLE IF EXISTS ibex_service`)
}

func seedOrgWithSession(t *testing.T, db *sql.DB, slug string) (orgID, sessionID uuid.UUID) {
	t.Helper()
	ctx := context.Background()
	tx, err := db.BeginTx(ctx, nil)
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = tx.Rollback() }()
	if _, err := tx.ExecContext(ctx, `SELECT set_config('app.is_service_account', 'true', true)`); err != nil {
		t.Fatalf("service account: %v", err)
	}
	if err := tx.QueryRowContext(ctx,
		`INSERT INTO ibex_core.organizations (name, slug) VALUES ($1, $2) RETURNING id`,
		"relay-org-"+slug, slug).Scan(&orgID); err != nil {
		t.Fatalf("org: %v", err)
	}
	var userID uuid.UUID
	if err := tx.QueryRowContext(ctx,
		`INSERT INTO ibex_core.users (org_id, email, name) VALUES ($1, $2, $3) RETURNING id`,
		orgID, uuid.NewString()+"@example.com", "relay-user").Scan(&userID); err != nil {
		t.Fatalf("user: %v", err)
	}
	var agentID uuid.UUID
	if err := tx.QueryRowContext(ctx,
		`INSERT INTO ibex_core.agents (org_id, created_by, name, slug) VALUES ($1, $2, $3, $4) RETURNING id`,
		orgID, userID, "relay-agent", uuid.NewString()[:8]).Scan(&agentID); err != nil {
		t.Fatalf("agent: %v", err)
	}
	if err := tx.QueryRowContext(ctx,
		`INSERT INTO ibex_core.sessions (org_id, agent_id, model, provider) VALUES ($1, $2, 'gpt-4o', 'openai') RETURNING id`,
		orgID, agentID).Scan(&sessionID); err != nil {
		t.Fatalf("session: %v", err)
	}
	if err := tx.Commit(); err != nil {
		t.Fatal(err)
	}
	return orgID, sessionID
}

func softDeleteSession(t *testing.T, db *sql.DB, sessionID uuid.UUID) {
	t.Helper()
	ctx := context.Background()
	tx, err := db.BeginTx(ctx, nil)
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = tx.Rollback() }()
	if _, err := tx.ExecContext(ctx, `SELECT set_config('app.is_service_account', 'true', true)`); err != nil {
		t.Fatalf("service account: %v", err)
	}
	if _, err := tx.ExecContext(ctx,
		`UPDATE ibex_core.sessions SET deleted_at = NOW() WHERE id = $1`, sessionID); err != nil {
		t.Fatalf("soft delete: %v", err)
	}
	if err := tx.Commit(); err != nil {
		t.Fatal(err)
	}
}

func fencedRunInput(orgID, sessionID uuid.UUID, version int64) evidenceoutbox.RunInput {
	f := &evidenceoutbox.TombstoneFence{
		ResourceType: fence.SessionResourceType, ResourceID: sessionID.String(), ResourceVersion: version,
	}
	return evidenceoutbox.RunInput{
		OrgID:          orgID,
		RequestID:      "req-" + uuid.NewString(),
		TraceID:        strings.ReplaceAll(uuid.NewString(), "-", ""),
		RootSpanID:     "1111111111111111",
		ModelID:        "gpt-4o",
		RedactionClass: evidenceoutbox.RedactionClassMetadata,
		TombstoneFence: f,
		Producer: &evidenceoutbox.ProducerMetadata{
			Source: "relay-e2e", RedactionClass: evidenceoutbox.RedactionClassMetadata,
			RedactionProofVersion: "v1",
			ResourceType:          fence.SessionResourceType, ResourceID: sessionID.String(), ResourceVersion: version,
		},
	}
}

type recordingFencedDeliverer struct {
	checker *fence.SessionFenceChecker
	mu      sync.Mutex
	rows    []string
}

func (d *recordingFencedDeliverer) DeliverWithTombstoneFence(ctx context.Context, row evidenceoutbox.OutboxRow, f evidenceoutbox.TombstoneFence) error {
	if err := d.checker.CheckFence(ctx, row.OrgID, f); err != nil {
		return err
	}
	d.mu.Lock()
	defer d.mu.Unlock()
	d.rows = append(d.rows, row.ID.String())
	return nil
}

type integrationFencedDeliverer struct {
	inner *recordingFencedDeliverer
}

func (d integrationFencedDeliverer) Deliver(ctx context.Context, row evidenceoutbox.OutboxRow) error {
	if row.TombstoneFence == nil {
		return errors.New("relay e2e: row is missing tombstone fence")
	}
	return d.inner.DeliverWithTombstoneFence(ctx, row, *row.TombstoneFence)
}

func (d integrationFencedDeliverer) DeliverWithTombstoneFence(ctx context.Context, row evidenceoutbox.OutboxRow, f evidenceoutbox.TombstoneFence) error {
	return d.inner.DeliverWithTombstoneFence(ctx, row, f)
}

func TestIntegration_OpenRelayDB_PinsRelayRole(t *testing.T) {
	_ = openMigratedDB(t)
	ctx := context.Background()
	pinned, err := openRelayDB(ctx, integrationDSN(), 5*time.Second)
	if err != nil {
		t.Fatalf("openRelayDB: %v", err)
	}
	t.Cleanup(func() { _ = pinned.Close() })

	var currentUser, sessionUser string
	if err := pinned.QueryRowContext(ctx, `SELECT current_user, session_user`).Scan(&currentUser, &sessionUser); err != nil {
		t.Fatal(err)
	}
	if currentUser != relayRoleName {
		t.Fatalf("current_user: got %q want %q", currentUser, relayRoleName)
	}
	if sessionUser == relayRoleName {
		t.Fatal("helper login role must remain the session user")
	}

	var count int
	err = pinned.QueryRowContext(ctx, `SELECT COUNT(*) FROM ibex_core.sessions`).Scan(&count)
	if err == nil {
		t.Fatal("relay role must not read sessions directly")
	}

	var outcome string
	if err := pinned.QueryRowContext(ctx,
		`SELECT ibex_core.evidence_outbox_check_session_fence($1, $2, $3)`,
		uuid.New(), uuid.New(), int64(1)).Scan(&outcome); err != nil {
		t.Fatalf("fence helper must be executable: %v", err)
	}
	if outcome != "not_found" {
		t.Fatalf("outcome: got %q want not_found", outcome)
	}
}

func TestIntegration_RelayDeliversFencedRowAndPoisonsTombstoned(t *testing.T) {
	admin := openMigratedDB(t)
	orgID, sessionID := seedOrgWithSession(t, admin, "relay-e2e")
	ctx := context.Background()
	pinned, err := openRelayDB(ctx, integrationDSN(), 5*time.Second)
	if err != nil {
		t.Fatalf("openRelayDB: %v", err)
	}
	t.Cleanup(func() { _ = pinned.Close() })

	store, err := evidenceoutbox.NewStore(admin)
	if err != nil {
		t.Fatal(err)
	}
	reg := ibexmetrics.NewRelay("test-relay")
	checker, err := fence.NewSessionFenceChecker(pinned, reg)
	if err != nil {
		t.Fatal(err)
	}
	recorder := &recordingFencedDeliverer{checker: checker}
	relay, err := evidenceoutbox.NewRelay(pinned, integrationFencedDeliverer{inner: recorder},
		evidenceoutbox.RelayConfig{BatchSize: 16, MaxAttempts: 3})
	if err != nil {
		t.Fatal(err)
	}

	persisted, err := store.PersistRun(ctx, fencedRunInput(orgID, sessionID, 1))
	if err != nil {
		t.Fatalf("persist: %v", err)
	}
	if len(persisted.OutboxIDs) == 0 {
		t.Fatal("expected outbox rows")
	}
	batch, err := relay.ProcessBatch(ctx)
	if err != nil {
		t.Fatalf("process: %v", err)
	}
	if batch.Claimed != len(persisted.OutboxIDs) || batch.Delivered != len(persisted.OutboxIDs) {
		t.Fatalf("batch: %+v want claimed=delivered=%d", batch, len(persisted.OutboxIDs))
	}
	if len(recorder.rows) != len(persisted.OutboxIDs) {
		t.Fatalf("delivered rows: got %d want %d", len(recorder.rows), len(persisted.OutboxIDs))
	}

	softDeleteSession(t, admin, sessionID)
	persisted2, err := store.PersistRun(ctx, fencedRunInput(orgID, sessionID, 1))
	if err != nil {
		t.Fatalf("persist after tombstone: %v", err)
	}
	batch2, err := relay.ProcessBatch(ctx)
	if err != nil {
		t.Fatalf("process after tombstone: %v", err)
	}
	if batch2.Claimed != len(persisted2.OutboxIDs) || batch2.Poisoned != len(persisted2.OutboxIDs) {
		t.Fatalf("tombstoned batch: %+v want claimed=poisoned=%d", batch2, len(persisted2.OutboxIDs))
	}
	if len(recorder.rows) != len(persisted.OutboxIDs) {
		t.Fatalf("poisoned rows must not be delivered: got %d deliveries", len(recorder.rows))
	}

	var poisoned int
	if err := admin.QueryRowContext(ctx,
		`SELECT COUNT(*) FROM ibex_core.evidence_outbox WHERE delivery_status = 'poison'`).Scan(&poisoned); err != nil {
		t.Fatal(err)
	}
	if poisoned != len(persisted2.OutboxIDs) {
		t.Fatalf("poison rows: got %d want %d", poisoned, len(persisted2.OutboxIDs))
	}
}

func TestIntegration_RecoverInFlightWithPinnedRole(t *testing.T) {
	admin := openMigratedDB(t)
	orgID, sessionID := seedOrgWithSession(t, admin, "relay-recover")
	ctx := context.Background()
	pinned, err := openRelayDB(ctx, integrationDSN(), 5*time.Second)
	if err != nil {
		t.Fatalf("openRelayDB: %v", err)
	}
	t.Cleanup(func() { _ = pinned.Close() })

	store, err := evidenceoutbox.NewStore(admin)
	if err != nil {
		t.Fatal(err)
	}
	reg := ibexmetrics.NewRelay("test-relay")
	checker, err := fence.NewSessionFenceChecker(pinned, reg)
	if err != nil {
		t.Fatal(err)
	}
	recorder := &recordingFencedDeliverer{checker: checker}
	relay, err := evidenceoutbox.NewRelay(pinned, integrationFencedDeliverer{inner: recorder},
		evidenceoutbox.RelayConfig{BatchSize: 16, MaxAttempts: 3})
	if err != nil {
		t.Fatal(err)
	}
	persisted, err := store.PersistRun(ctx, fencedRunInput(orgID, sessionID, 1))
	if err != nil {
		t.Fatalf("persist: %v", err)
	}
	if _, err := admin.ExecContext(ctx, `
UPDATE ibex_core.evidence_outbox
SET delivery_status = 'in_flight', attempts = 1, claimed_at = NOW() - INTERVAL '1 hour'
WHERE id = ANY($1)`, pq.Array(persisted.OutboxIDs)); err != nil {
		t.Fatalf("force in-flight: %v", err)
	}
	recovered, err := relay.RecoverInFlight(ctx, time.Nanosecond)
	if err != nil {
		t.Fatalf("recover: %v", err)
	}
	if recovered != int64(len(persisted.OutboxIDs)) {
		t.Fatalf("recovered: got %d want %d", recovered, len(persisted.OutboxIDs))
	}
	batch, err := relay.ProcessBatch(ctx)
	if err != nil {
		t.Fatalf("process: %v", err)
	}
	if batch.Delivered != len(persisted.OutboxIDs) {
		t.Fatalf("delivered after recover: got %d want %d", batch.Delivered, len(persisted.OutboxIDs))
	}
}
