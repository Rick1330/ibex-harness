//go:build integration

package session_test

import (
	"context"
	"database/sql"
	"errors"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/session"
	"github.com/google/uuid"
)

const maxAbandonIdleLimit = 5000

type abandonIdleExpect struct {
	skip  bool
	count int
}

func TestStore_AbandonIdle_MarksStaleActive(t *testing.T) {
	ids := setupStore(t)
	stale := mustCreate(t, ids, "ext-stale")
	fresh := mustCreate(t, ids, "ext-fresh")
	backdateSessionUpdatedAt(t, ids.db, stale.ID, time.Now().UTC().Add(-2*time.Hour))

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	res, err := ids.store.AbandonIdle(ctx, session.AbandonIdleParams{
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
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	if _, err := ids.store.Complete(ctx, sess.ID, ids.orgID); err != nil {
		t.Fatalf("complete: %v", err)
	}
	backdateSessionUpdatedAt(t, ids.db, sess.ID, time.Now().UTC().Add(-2*time.Hour))

	res, err := ids.store.AbandonIdle(ctx, session.AbandonIdleParams{
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
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if _, err := ids.store.AbandonIdle(ctx, session.AbandonIdleParams{}); err == nil {
		t.Fatal("expected IdleBefore validation error")
	}
}

func TestStore_AbandonIdle_EmptySkipAndClamp(t *testing.T) {
	cases := []struct {
		name   string
		params session.AbandonIdleParams
		prep   func(*testing.T, storeIDs)
		want   abandonIdleExpect
	}{
		{
			name: "empty_when_no_victims",
			params: session.AbandonIdleParams{
				IdleBefore: time.Now().UTC().Add(-time.Hour),
			},
		},
		{
			name: "skips_when_lock_held",
			params: session.AbandonIdleParams{
				IdleBefore: time.Now().UTC(),
			},
			prep: func(t *testing.T, ids storeIDs) {
				holdSweepLock(t, ids.db)
			},
			want: abandonIdleExpect{skip: true},
		},
	}

	for _, tc := range cases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			ids := setupStore(t)
			if tc.prep != nil {
				tc.prep(t, ids)
			}
			assertAbandonIdleOutcome(t, ids.store, tc.params, tc.want)
		})
	}
}

func TestStore_AbandonIdle_ClampHighLimit(t *testing.T) {
	ids := setupStore(t)
	for i := 0; i < maxAbandonIdleLimit+5; i++ {
		sess := mustCreate(t, ids, "ext-clamp-"+uuid.NewString())
		backdateSessionUpdatedAt(t, ids.db, sess.ID, time.Now().UTC().Add(-2*time.Hour))
	}
	assertAbandonIdleOutcome(t, ids.store, session.AbandonIdleParams{
		IdleBefore: time.Now().UTC().Add(-30 * time.Minute),
		Limit:      100_000,
	}, abandonIdleExpect{count: maxAbandonIdleLimit})
}

func assertAbandonIdleOutcome(
	t *testing.T,
	store *session.PostgresStore,
	params session.AbandonIdleParams,
	want abandonIdleExpect,
) {
	t.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	res, err := store.AbandonIdle(ctx, params)
	if err != nil {
		t.Fatalf("AbandonIdle: %v", err)
	}
	if res.SkippedLock != want.skip {
		t.Fatalf("SkippedLock=%v want %v", res.SkippedLock, want.skip)
	}
	if res.Count() != want.count {
		t.Fatalf("Count=%d want %d", res.Count(), want.count)
	}
}

func TestStore_AbandonIdle_NullExternalID(t *testing.T) {
	ids := setupStore(t)
	sess := mustCreate(t, ids, "")
	backdateSessionUpdatedAt(t, ids.db, sess.ID, time.Now().UTC().Add(-2*time.Hour))
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	res, err := ids.store.AbandonIdle(ctx, session.AbandonIdleParams{
		IdleBefore: time.Now().UTC().Add(-30 * time.Minute),
	})
	if err != nil {
		t.Fatalf("AbandonIdle: %v", err)
	}
	row := mustFindAbandoned(t, res.Abandoned, sess.ID)
	if row.ExternalID != nil {
		t.Fatalf("expected nil external_id, got %q", *row.ExternalID)
	}
}

func holdSweepLock(t *testing.T, db *sql.DB) {
	t.Helper()
	// Background: the transaction must stay open until t.Cleanup rolls it back.
	ctx := context.Background()
	tx, err := db.BeginTx(ctx, nil)
	if err != nil {
		t.Fatalf("begin: %v", err)
	}
	t.Cleanup(func() {
		if err := tx.Rollback(); err != nil && !errors.Is(err, sql.ErrTxDone) {
			t.Errorf("rollback sweep-lock transaction: %v", err)
		}
	})
	if _, err := tx.ExecContext(ctx, `SELECT set_config('app.is_service_account', 'true', true)`); err != nil {
		t.Fatalf("sa: %v", err)
	}
	var acquired bool
	err = tx.QueryRowContext(ctx, `SELECT pg_try_advisory_xact_lock($1)`,
		session.SweepAdvisoryLockKey).Scan(&acquired)
	if err != nil {
		t.Fatalf("lock: %v", err)
	}
	if !acquired {
		t.Fatal("failed to acquire sweep lock")
	}
}

func mustFindAbandoned(t *testing.T, rows []session.AbandonedSession, id uuid.UUID) session.AbandonedSession {
	t.Helper()
	for _, r := range rows {
		if r.SessionID == id {
			return r
		}
	}
	t.Fatalf("missing abandoned session %s in %+v", id, rows)
	return session.AbandonedSession{}
}

func backdateSessionUpdatedAt(t *testing.T, db *sql.DB, sessionID uuid.UUID, when time.Time) {
	t.Helper()
	ctx := context.Background()
	err := withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		// Avoid DISABLE TRIGGER (ACCESS EXCLUSIVE). Replica role skips user triggers.
		if _, err := tx.ExecContext(ctx, `SELECT set_config('session_replication_role', 'replica', true)`); err != nil {
			return err
		}
		_, err := tx.ExecContext(ctx,
			`UPDATE ibex_core.sessions SET updated_at = $1 WHERE id = $2::uuid`,
			when.UTC(), sessionID)
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
