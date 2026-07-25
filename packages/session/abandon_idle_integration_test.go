//go:build integration

package session_test

import (
	"context"
	"database/sql"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/session"
	"github.com/google/uuid"
)

func TestStore_AbandonIdle_MarksStaleActive(t *testing.T) {
	ids := setupStore(t)
	stale := mustCreate(t, ids, "ext-stale")
	fresh := mustCreate(t, ids, "ext-fresh")
	backdateSessionUpdatedAt(t, ids.db, stale.ID, time.Now().UTC().Add(-2*time.Hour))

	res, err := ids.store.AbandonIdle(context.Background(), session.AbandonIdleParams{
		IdleBefore: time.Now().UTC().Add(-30 * time.Minute),
		Limit:      100,
	})
	if err != nil {
		t.Fatalf("AbandonIdle: %v", err)
	}
	if res.SkippedLock {
		t.Fatal("unexpected skip lock")
	}
	if !containsAbandoned(res.Abandoned, stale.ID) {
		t.Fatalf("missing stale session in %+v", res.Abandoned)
	}
	if containsAbandoned(res.Abandoned, fresh.ID) {
		t.Fatal("fresh session should not be abandoned")
	}

	got := mustReload(t, ids, "ext-stale")
	if got.Status != session.StatusAbandoned {
		t.Fatalf("status=%s", got.Status)
	}
	still := mustReload(t, ids, "ext-fresh")
	if still.Status != session.StatusActive {
		t.Fatalf("fresh status=%s", still.Status)
	}
}

func TestStore_AbandonIdle_SkipsCompleted(t *testing.T) {
	ids := setupStore(t)
	sess := mustCreate(t, ids, "ext-done-idle")
	if err := ids.store.Complete(context.Background(), sess.ID, ids.orgID); err != nil {
		t.Fatalf("complete: %v", err)
	}
	backdateSessionUpdatedAt(t, ids.db, sess.ID, time.Now().UTC().Add(-2*time.Hour))

	res, err := ids.store.AbandonIdle(context.Background(), session.AbandonIdleParams{
		IdleBefore: time.Now().UTC().Add(-30 * time.Minute),
	})
	if err != nil {
		t.Fatalf("AbandonIdle: %v", err)
	}
	if containsAbandoned(res.Abandoned, sess.ID) {
		t.Fatal("completed session must not be abandoned")
	}
}

func TestStore_AbandonIdle_RequiresIdleBefore(t *testing.T) {
	ids := setupStore(t)
	if _, err := ids.store.AbandonIdle(context.Background(), session.AbandonIdleParams{}); err == nil {
		t.Fatal("expected IdleBefore validation error")
	}
}

func backdateSessionUpdatedAt(t *testing.T, db *sql.DB, sessionID uuid.UUID, when time.Time) {
	t.Helper()
	ctx := context.Background()
	err := withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		if _, err := tx.ExecContext(ctx,
			`ALTER TABLE ibex_core.sessions DISABLE TRIGGER sessions_updated_at`); err != nil {
			return err
		}
		_, err := tx.ExecContext(ctx,
			`UPDATE ibex_core.sessions SET updated_at = $1 WHERE id = $2::uuid`,
			when.UTC(), sessionID)
		if err != nil {
			return err
		}
		_, err = tx.ExecContext(ctx,
			`ALTER TABLE ibex_core.sessions ENABLE TRIGGER sessions_updated_at`)
		return err
	})
	if err != nil {
		t.Fatalf("backdate updated_at: %v", err)
	}
}

func containsAbandoned(rows []session.AbandonedSession, id uuid.UUID) bool {
	for _, r := range rows {
		if r.SessionID == id {
			return true
		}
	}
	return false
}
