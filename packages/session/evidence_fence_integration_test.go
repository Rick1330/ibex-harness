//go:build integration

package session_test

import (
	"context"
	"database/sql"
	"errors"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/session"
	"github.com/google/uuid"
)

func TestStore_LookupEvidenceFence_TenantScopeAndSoftDeleteVersion(t *testing.T) {
	ids := setupStore(t)
	sess := mustCreate(t, ids, "ext-evidence-fence")

	fence, err := ids.store.LookupEvidenceFence(context.Background(), ids.orgID, sess.ID)
	if err != nil {
		t.Fatalf("lookup active fence: %v", err)
	}
	if fence.ResourceType != "session" || fence.ResourceID != sess.ID || fence.ResourceVersion != 1 {
		t.Fatalf("unexpected fence: %+v", fence)
	}

	if _, err := ids.store.LookupEvidenceFence(context.Background(), uuid.New(), sess.ID); !errors.Is(err, session.ErrEvidenceFenceNotFound) {
		t.Fatalf("cross-tenant lookup error=%v want ErrEvidenceFenceNotFound", err)
	}

	softDeleteSession(t, ids, sess.ID)
	var version int64
	if err := withServiceAccount(context.Background(), ids.db, func(tx *sql.Tx) error {
		return tx.QueryRowContext(context.Background(), `SELECT evidence_fence_version FROM ibex_core.sessions WHERE id = $1 AND org_id = $2`, sess.ID, ids.orgID).Scan(&version)
	}); err != nil {
		t.Fatalf("read deleted fence version: %v", err)
	}
	if version != fence.ResourceVersion+1 {
		t.Fatalf("deleted version=%d want %d", version, fence.ResourceVersion+1)
	}
	if _, err := ids.store.LookupEvidenceFence(context.Background(), ids.orgID, sess.ID); !errors.Is(err, session.ErrEvidenceFenceNotFound) {
		t.Fatalf("deleted session lookup error=%v want ErrEvidenceFenceNotFound", err)
	}

	if err := withServiceAccount(context.Background(), ids.db, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(context.Background(), `UPDATE ibex_core.sessions SET deleted_at = NULL WHERE id = $1 AND org_id = $2`, sess.ID, ids.orgID)
		return err
	}); err == nil {
		t.Fatal("soft-delete tombstone was cleared")
	}
}
