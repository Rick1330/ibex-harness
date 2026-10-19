//go:build integration

package bootstrap

import (
	"context"
	"database/sql"
	"errors"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/evidenceoutbox"
	ibexmetrics "github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/services/relay/internal/fence"
	"github.com/Rick1330/ibex-harness/services/relay/internal/relaytest"
	"github.com/google/uuid"
)

func fencedRunInput(orgID, sessionID uuid.UUID, version int64) evidenceoutbox.RunInput {
	fenceRef := relaytest.NewFence(sessionID, version)
	return evidenceoutbox.RunInput{
		OrgID:          orgID,
		RequestID:      "req-" + uuid.NewString(),
		TraceID:        strings.ReplaceAll(uuid.NewString(), "-", ""),
		RootSpanID:     "1111111111111111",
		ModelID:        "gpt-4o",
		RedactionClass: evidenceoutbox.RedactionClassMetadata,
		TombstoneFence: &fenceRef,
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

func (d *recordingFencedDeliverer) delivered() []string {
	d.mu.Lock()
	defer d.mu.Unlock()
	return append([]string(nil), d.rows...)
}

func (d *recordingFencedDeliverer) reset() {
	d.mu.Lock()
	defer d.mu.Unlock()
	d.rows = nil
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

// relayHarness bundles the admin pool, the role-pinned relay pool, and the
// relay under test for the integration cases.
type relayHarness struct {
	admin    *sql.DB
	pinned   *sql.DB
	store    *evidenceoutbox.Store
	relay    *evidenceoutbox.Relay
	recorder *recordingFencedDeliverer
}

func newRelayHarness(t *testing.T, admin *sql.DB) *relayHarness {
	t.Helper()
	ctx := context.Background()
	pinned, err := openRelayDB(ctx, relaytest.DSN(), 5*time.Second)
	if err != nil {
		t.Fatalf("openRelayDB: %v", err)
	}
	t.Cleanup(func() { _ = pinned.Close() })
	store, err := evidenceoutbox.NewStore(admin)
	if err != nil {
		t.Fatal(err)
	}
	checker, err := fence.NewSessionFenceChecker(pinned, ibexmetrics.NewRelay("test-relay"))
	if err != nil {
		t.Fatal(err)
	}
	recorder := &recordingFencedDeliverer{checker: checker}
	relay, err := evidenceoutbox.NewRelay(pinned, integrationFencedDeliverer{inner: recorder},
		evidenceoutbox.RelayConfig{BatchSize: 16, MaxAttempts: 3})
	if err != nil {
		t.Fatal(err)
	}
	return &relayHarness{admin: admin, pinned: pinned, store: store, relay: relay, recorder: recorder}
}

func TestIntegration_OpenRelayDB_PinsRelayRole(t *testing.T) {
	_ = relaytest.OpenMigratedDB(t)
	ctx := context.Background()
	pinned, err := openRelayDB(ctx, relaytest.DSN(), 5*time.Second)
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
	admin := relaytest.OpenMigratedDB(t)
	orgID, sessionID := relaytest.SeedOrgWithSession(t, admin, "relay-e2e")
	ctx := context.Background()
	h := newRelayHarness(t, admin)

	persisted, err := h.store.PersistRun(ctx, fencedRunInput(orgID, sessionID, 1))
	if err != nil {
		t.Fatalf("persist: %v", err)
	}
	if len(persisted.OutboxIDs) == 0 {
		t.Fatal("expected outbox rows")
	}
	batch, err := h.relay.ProcessBatch(ctx)
	if err != nil {
		t.Fatalf("process: %v", err)
	}
	assertDelivered(t, batch, persisted.OutboxIDs, h.recorder)
	h.recorder.reset()

	relaytest.SoftDeleteSession(t, admin, sessionID)
	persisted2, err := h.store.PersistRun(ctx, fencedRunInput(orgID, sessionID, 1))
	if err != nil {
		t.Fatalf("persist after tombstone: %v", err)
	}
	batch2, err := h.relay.ProcessBatch(ctx)
	if err != nil {
		t.Fatalf("process after tombstone: %v", err)
	}
	assertPoisoned(t, batch2, persisted2.OutboxIDs, h.recorder)
	assertPoisonRows(t, admin, len(persisted2.OutboxIDs))
}

func assertDelivered(t *testing.T, batch evidenceoutbox.RelayBatchResult, ids []uuid.UUID, recorder *recordingFencedDeliverer) {
	t.Helper()
	if batch.Claimed != len(ids) || batch.Delivered != len(ids) {
		t.Fatalf("batch: %+v want claimed=delivered=%d", batch, len(ids))
	}
	if got := len(recorder.delivered()); got != len(ids) {
		t.Fatalf("delivered rows: got %d want %d", got, len(ids))
	}
}

func assertPoisoned(t *testing.T, batch evidenceoutbox.RelayBatchResult, ids []uuid.UUID, recorder *recordingFencedDeliverer) {
	t.Helper()
	if batch.Claimed != len(ids) || batch.Poisoned != len(ids) {
		t.Fatalf("tombstoned batch: %+v want claimed=poisoned=%d", batch, len(ids))
	}
	if got := len(recorder.delivered()); got != 0 {
		t.Fatalf("poisoned rows must not be delivered: got %d deliveries", got)
	}
}

func assertPoisonRows(t *testing.T, admin *sql.DB, want int) {
	t.Helper()
	var poisoned int
	if err := admin.QueryRowContext(context.Background(),
		`SELECT COUNT(*) FROM ibex_core.evidence_outbox WHERE delivery_status = 'poison'`).Scan(&poisoned); err != nil {
		t.Fatal(err)
	}
	if poisoned != want {
		t.Fatalf("poison rows: got %d want %d", poisoned, want)
	}
}

func TestIntegration_RecoverInFlightWithPinnedRole(t *testing.T) {
	admin := relaytest.OpenMigratedDB(t)
	orgID, sessionID := relaytest.SeedOrgWithSession(t, admin, "relay-recover")
	ctx := context.Background()
	h := newRelayHarness(t, admin)

	persisted, err := h.store.PersistRun(ctx, fencedRunInput(orgID, sessionID, 1))
	if err != nil {
		t.Fatalf("persist: %v", err)
	}
	forceInFlightForOrg(t, admin, orgID)

	recovered, err := h.relay.RecoverInFlight(ctx, time.Nanosecond)
	if err != nil {
		t.Fatalf("recover: %v", err)
	}
	if recovered != int64(len(persisted.OutboxIDs)) {
		t.Fatalf("recovered: got %d want %d", recovered, len(persisted.OutboxIDs))
	}
	batch, err := h.relay.ProcessBatch(ctx)
	if err != nil {
		t.Fatalf("process: %v", err)
	}
	if batch.Delivered != len(persisted.OutboxIDs) {
		t.Fatalf("delivered after recover: got %d want %d", batch.Delivered, len(persisted.OutboxIDs))
	}
}

// forceInFlightForOrg marks every outbox row for the org as an abandoned
// in-flight claim. The migrated schema is reset per test, so the org's rows are
// exactly those persisted by the test.
func forceInFlightForOrg(t *testing.T, admin *sql.DB, orgID uuid.UUID) {
	t.Helper()
	if _, err := admin.ExecContext(context.Background(),
		`UPDATE ibex_core.evidence_outbox SET delivery_status = 'in_flight', attempts = 1, claimed_at = NOW() - INTERVAL '1 hour' WHERE org_id = $1`,
		orgID); err != nil {
		t.Fatalf("force in-flight: %v", err)
	}
}
