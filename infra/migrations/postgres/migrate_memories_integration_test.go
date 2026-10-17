//go:build integration

package postgres

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"strings"
	"testing"
	"time"

	"github.com/lib/pq"
)

const insertMemoryWithSessionSQL = `
	INSERT INTO ibex_core.memories (
		org_id, agent_id, session_id, content, content_hash, content_tokens
	) VALUES (
		$1::uuid, $2::uuid, $3::uuid, $4, $5, $6
	)
	RETURNING id::text`

const insertMemoryMinimalSQL = `
	INSERT INTO ibex_core.memories (
		org_id, agent_id, content, content_hash, content_tokens
	) VALUES (
		$1::uuid, $2::uuid, $3, $4, $5
	)
	RETURNING id::text, valid_from, valid_until, observed_at`

func TestMemories_TemporalColumnsAndDefaults(t *testing.T) {
	dsn := testDSN()
	db := openTestDB(t)
	defer db.Close()
	resetSchema(t, db)
	if err := Up(dsn); err != nil {
		t.Fatalf("up: %v", err)
	}

	ctx := context.Background()
	assertMemoryTemporalColumns(t, ctx, db)

	orgA, _ := seedTwoOrgsWithAgents(t, ctx, db)
	agentID := lookupAgentID(t, ctx, agentLookup{db: db, orgID: orgA, slug: "agent-a"})

	var id string
	var validFrom, observedAt time.Time
	var validUntil sql.NullTime
	err := withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		return tx.QueryRowContext(ctx, insertMemoryMinimalSQL,
			orgA, agentID, "user prefers dark mode", "hash-defaults-1", 4,
		).Scan(&id, &validFrom, &validUntil, &observedAt)
	})
	if err != nil {
		t.Fatalf("insert minimal memory: %v", err)
	}
	if id == "" {
		t.Fatal("expected memory id")
	}
	if validUntil.Valid {
		t.Fatal("expected valid_until NULL by default")
	}
	if validFrom.IsZero() || observedAt.IsZero() {
		t.Fatal("expected valid_from and observed_at defaults")
	}
}

func TestMemories_ValidIntervalCheck(t *testing.T) {
	dsn := testDSN()
	db := openTestDB(t)
	defer db.Close()
	resetSchema(t, db)
	if err := Up(dsn); err != nil {
		t.Fatalf("up: %v", err)
	}

	ctx := context.Background()
	orgA, _ := seedTwoOrgsWithAgents(t, ctx, db)
	agentID := lookupAgentID(t, ctx, agentLookup{db: db, orgID: orgA, slug: "agent-a"})

	from := time.Date(2024, 6, 1, 12, 0, 0, 0, time.UTC)
	until := from.Add(-time.Hour) // invalid: until <= from
	err := withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(ctx, `
			INSERT INTO ibex_core.memories (
				org_id, agent_id, content, content_hash, content_tokens,
				valid_from, valid_until
			) VALUES ($1::uuid, $2::uuid, 'bad interval', 'hash-bad-interval', 2, $3, $4)`,
			orgA, agentID, from, until)
		return err
	})
	if err == nil {
		t.Fatal("expected valid_interval CHECK to reject valid_until <= valid_from")
	}
	var pqErr *pq.Error
	if !errors.As(err, &pqErr) || pqErr.Code != "23514" {
		t.Fatalf("expected check_violation 23514, got %v", err)
	}

	// Equal timestamps also rejected (need strictly greater).
	err = withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(ctx, `
			INSERT INTO ibex_core.memories (
				org_id, agent_id, content, content_hash, content_tokens,
				valid_from, valid_until
			) VALUES ($1::uuid, $2::uuid, 'equal interval', 'hash-eq-interval', 2, $3, $3)`,
			orgA, agentID, from)
		return err
	})
	if err == nil {
		t.Fatal("expected valid_interval CHECK to reject valid_until = valid_from")
	}
}

func TestMemories_RetrospectiveValidFrom(t *testing.T) {
	dsn := testDSN()
	db := openTestDB(t)
	defer db.Close()
	resetSchema(t, db)
	if err := Up(dsn); err != nil {
		t.Fatalf("up: %v", err)
	}

	ctx := context.Background()
	orgA, _ := seedTwoOrgsWithAgents(t, ctx, db)
	agentID := lookupAgentID(t, ctx, agentLookup{db: db, orgID: orgA, slug: "agent-a"})

	validFrom := time.Now().UTC().Add(-3 * 365 * 24 * time.Hour)
	observedAt := time.Now().UTC()
	var id string
	err := withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		return tx.QueryRowContext(ctx, `
			INSERT INTO ibex_core.memories (
				org_id, agent_id, content, content_hash, content_tokens,
				valid_from, observed_at
			) VALUES ($1::uuid, $2::uuid, 'moved to Berlin three years ago', 'hash-berlin', 6, $3, $4)
			RETURNING id::text`,
			orgA, agentID, validFrom, observedAt).Scan(&id)
	})
	if err != nil {
		t.Fatalf("retrospective insert: %v", err)
	}
	if id == "" {
		t.Fatal("expected memory id")
	}
}

func TestRLSMemoriesIsolation(t *testing.T) {
	dsn := testDSN()
	db := openTestDB(t)
	defer db.Close()
	resetSchema(t, db)
	if err := Up(dsn); err != nil {
		t.Fatalf("up: %v", err)
	}

	ctx := context.Background()
	orgA, orgB := seedTwoOrgsWithAgents(t, ctx, db)
	seedMemory(t, ctx, memorySeed{db: db, orgID: orgA, agentSlug: "agent-a", content: "mem-a"})
	seedMemory(t, ctx, memorySeed{db: db, orgID: orgB, agentSlug: "agent-b", content: "mem-b"})

	assertTableCount(t, ctx, tableCountCheck{db: db, table: "memories", orgID: "", want: 0})
	assertTableCount(t, ctx, tableCountCheck{db: db, table: "memories", orgID: orgA, want: 1})
	assertTableCount(t, ctx, tableCountCheck{db: db, table: "memories", orgID: orgB, want: 1})

	// Service account sees all rows.
	var serviceCount int
	err := withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		return tx.QueryRowContext(ctx, `SELECT COUNT(*) FROM ibex_core.memories`).Scan(&serviceCount)
	})
	if err != nil {
		t.Fatalf("service count: %v", err)
	}
	if serviceCount != 2 {
		t.Fatalf("expected service account count 2, got %d", serviceCount)
	}
}

func TestMemories_SoftDeletePartialIndex(t *testing.T) {
	dsn := testDSN()
	db := openTestDB(t)
	defer db.Close()
	resetSchema(t, db)
	if err := Up(dsn); err != nil {
		t.Fatalf("up: %v", err)
	}

	ctx := context.Background()
	orgA, _ := seedTwoOrgsWithAgents(t, ctx, db)
	memID := seedMemory(t, ctx, memorySeed{db: db, orgID: orgA, agentSlug: "agent-a", content: "active-then-deleted"})

	err := withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(ctx, `
			UPDATE ibex_core.memories
			SET status = 'deleted', deleted_at = NOW()
			WHERE id = $1::uuid`, memID)
		return err
	})
	if err != nil {
		t.Fatalf("soft delete: %v", err)
	}

	var activeCount int
	err = withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		return tx.QueryRowContext(ctx, `
			SELECT COUNT(*) FROM ibex_core.memories
			WHERE org_id = $1::uuid AND status = 'active' AND deleted_at IS NULL`,
			orgA).Scan(&activeCount)
	})
	if err != nil {
		t.Fatalf("active count: %v", err)
	}
	if activeCount != 0 {
		t.Fatalf("expected 0 active memories after soft delete, got %d", activeCount)
	}

	var idxExists bool
	err = db.QueryRowContext(ctx, `
		SELECT EXISTS (
			SELECT 1 FROM pg_indexes
			WHERE schemaname = 'ibex_core' AND indexname = 'idx_memories_agent_active'
		)`).Scan(&idxExists)
	if err != nil {
		t.Fatalf("index check: %v", err)
	}
	if !idxExists {
		t.Fatal("missing idx_memories_agent_active")
	}
}

func TestMemories_SessionClearOnDelete(t *testing.T) {
	dsn := testDSN()
	db := openTestDB(t)
	defer db.Close()
	resetSchema(t, db)
	if err := Up(dsn); err != nil {
		t.Fatalf("up: %v", err)
	}

	ctx := context.Background()
	orgA, _ := seedTwoOrgsWithAgents(t, ctx, db)
	sess := seedSessionWithCheckpoint(t, ctx, sessionSeed{
		db: db, orgID: orgA, agentSlug: "agent-a", externalID: "mem-sess",
	})

	var memID string
	err := withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		return tx.QueryRowContext(ctx, insertMemoryWithSessionSQL,
			orgA, sess.agentID, sess.sessionID,
			"session-scoped note", "hash-sess-mem", 3,
		).Scan(&memID)
	})
	if err != nil {
		t.Fatalf("insert memory with session: %v", err)
	}

	err = withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(ctx, `DELETE FROM ibex_core.sessions WHERE id = $1::uuid`, sess.sessionID)
		return err
	})
	if err != nil {
		t.Fatalf("delete session: %v", err)
	}

	var sessionID sql.NullString
	err = withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		return tx.QueryRowContext(ctx, `
			SELECT session_id::text FROM ibex_core.memories WHERE id = $1::uuid`, memID,
		).Scan(&sessionID)
	})
	if err != nil {
		t.Fatalf("lookup memory session_id: %v", err)
	}
	if sessionID.Valid {
		t.Fatalf("expected session_id NULL after session delete, got %q", sessionID.String)
	}
}

type memoryColExpect struct {
	name     string
	nullable string
	hasDef   bool
}

func assertMemoryTemporalColumns(t *testing.T, ctx context.Context, db *sql.DB) {
	t.Helper()
	assertMemoryTemporalColumnDefs(t, ctx, db)
	assertMemoriesForceRLS(t, ctx, db)
}

func assertMemoryTemporalColumnDefs(t *testing.T, ctx context.Context, db *sql.DB) {
	t.Helper()
	expects := []memoryColExpect{
		{name: "valid_from", nullable: "NO", hasDef: true},
		{name: "valid_until", nullable: "YES", hasDef: false},
		{name: "observed_at", nullable: "NO", hasDef: true},
	}
	for _, e := range expects {
		assertMemoryColumn(t, ctx, db, e)
	}
}

func assertMemoryColumn(t *testing.T, ctx context.Context, db *sql.DB, e memoryColExpect) {
	t.Helper()
	var dataType, isNullable string
	var columnDefault sql.NullString
	err := db.QueryRowContext(ctx, `
		SELECT data_type, is_nullable, column_default
		FROM information_schema.columns
		WHERE table_schema = 'ibex_core' AND table_name = 'memories' AND column_name = $1`,
		e.name).Scan(&dataType, &isNullable, &columnDefault)
	if err != nil {
		t.Fatalf("column %s: %v", e.name, err)
	}
	if dataType != "timestamp with time zone" {
		t.Errorf("column %s type=%q, want timestamptz", e.name, dataType)
	}
	if isNullable != e.nullable {
		t.Errorf("column %s nullable=%q, want %q", e.name, isNullable, e.nullable)
	}
	assertMemoryColumnDefault(t, e, columnDefault)
}

func assertMemoryColumnDefault(t *testing.T, e memoryColExpect, columnDefault sql.NullString) {
	t.Helper()
	if e.hasDef {
		if !columnDefault.Valid || columnDefault.String == "" {
			t.Errorf("column %s missing default", e.name)
		}
		return
	}
	if columnDefault.Valid && columnDefault.String != "" {
		t.Errorf("column %s unexpected default %q", e.name, columnDefault.String)
	}
}

func assertMemoriesForceRLS(t *testing.T, ctx context.Context, db *sql.DB) {
	t.Helper()
	assertCoreTableRLS(t, ctx, coreTableRLSCheck{
		db: db, table: "memories", expect: coreTableRLSFlags{forced: true},
	})
}

type memorySeed struct {
	db                        *sql.DB
	orgID, agentSlug, content string
}

func seedMemory(t *testing.T, ctx context.Context, seed memorySeed) string {
	t.Helper()
	var id string
	var validFrom, observedAt time.Time
	var validUntil sql.NullTime
	err := withServiceAccount(ctx, seed.db, func(tx *sql.Tx) error {
		var agentID string
		if err := tx.QueryRowContext(ctx, `
			SELECT id::text FROM ibex_core.agents
			WHERE org_id = $1::uuid AND slug = $2`, seed.orgID, seed.agentSlug).Scan(&agentID); err != nil {
			return err
		}
		return tx.QueryRowContext(ctx, insertMemoryMinimalSQL,
			seed.orgID, agentID, seed.content, "hash-"+seed.content, 1,
		).Scan(&id, &validFrom, &validUntil, &observedAt)
	})
	if err != nil {
		t.Fatalf("seed memory org=%s: %v", seed.orgID, err)
	}
	return id
}

func TestMemoryLifecycleOutbox_RLSLeastPrivilege(t *testing.T) {
	dsn := testDSN()
	db := openTestDB(t)
	defer db.Close()
	resetSchema(t, db)
	if err := Up(dsn); err != nil {
		t.Fatalf("up: %v", err)
	}
	ctx := context.Background()
	orgA, orgB := seedTwoOrgsWithAgents(t, ctx, db)
	memoryA := seedMemory(t, ctx, memorySeed{db: db, orgID: orgA, agentSlug: "agent-a", content: "outbox-a"})
	memoryB := seedMemory(t, ctx, memorySeed{db: db, orgID: orgB, agentSlug: "agent-b", content: "outbox-b"})
	if err := withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		for _, row := range [][2]string{{orgA, memoryA}, {orgB, memoryB}} {
			if _, err := tx.ExecContext(ctx, `
INSERT INTO ibex_core.memory_lifecycle_outbox
(org_id, memory_id, revision, event_type)
VALUES ($1::uuid, $2::uuid, 2, 'forgotten')`, row[0], row[1]); err != nil {
				return err
			}
		}
		return nil
	}); err != nil {
		t.Fatalf("seed lifecycle events: %v", err)
	}

	err := withOrgContext(ctx, db, orgA, func(tx *sql.Tx) error {
		var own, foreign int
		if err := tx.QueryRowContext(ctx, `SELECT COUNT(*) FROM ibex_core.memory_lifecycle_outbox WHERE org_id=$1::uuid`, orgA).Scan(&own); err != nil {
			return err
		}
		if err := tx.QueryRowContext(ctx, `SELECT COUNT(*) FROM ibex_core.memory_lifecycle_outbox WHERE org_id=$1::uuid`, orgB).Scan(&foreign); err != nil {
			return err
		}
		if own != 1 || foreign != 0 {
			return fmt.Errorf("ibex_app outbox visibility own=%d foreign=%d, want 1/0", own, foreign)
		}
		return nil
	})
	if err != nil {
		t.Fatalf("outbox RLS visibility: %v", err)
	}
	var updateErr error
	_ = withOrgContext(ctx, db, orgA, func(tx *sql.Tx) error {
		_, updateErr = tx.ExecContext(ctx, `UPDATE ibex_core.memory_lifecycle_outbox SET attempts=attempts+1 WHERE org_id=$1::uuid`, orgA)
		return nil
	}) // PostgreSQL aborts the denied statement's transaction; helper rolls it back.
	if updateErr == nil {
		t.Fatal("ibex_app unexpectedly updated relay-owned outbox state")
	}
}

func TestMemoryLifecycleRevision_TombstoneIsTerminal(t *testing.T) {
	dsn := testDSN()
	db := openTestDB(t)
	defer db.Close()
	resetSchema(t, db)
	if err := Up(dsn); err != nil {
		t.Fatalf("up: %v", err)
	}
	ctx := context.Background()
	orgA, _ := seedTwoOrgsWithAgents(t, ctx, db)
	memoryID := seedMemory(t, ctx, memorySeed{db: db, orgID: orgA, agentSlug: "agent-a", content: "terminal tombstone"})
	var revision int64
	if err := withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		return tx.QueryRowContext(ctx, `
UPDATE ibex_core.memories
SET status='deleted', deleted_at=NOW(), tombstoned=TRUE
WHERE id=$1::uuid RETURNING lifecycle_revision`, memoryID).Scan(&revision)
	}); err != nil {
		t.Fatalf("forget memory: %v", err)
	}
	if revision != 2 {
		t.Fatalf("lifecycle revision=%d, want 2", revision)
	}
	err := withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(ctx, `UPDATE ibex_core.memories SET tombstoned=FALSE, status='active', deleted_at=NULL WHERE id=$1::uuid`, memoryID)
		return err
	})
	if err == nil {
		t.Fatal("expected terminal tombstone trigger to reject resurrection")
	}
	var pqErr *pq.Error
	if !errors.As(err, &pqErr) || pqErr.Code != "P0001" {
		t.Fatalf("expected terminal tombstone exception, got %v", err)
	}
	var stillTombstoned bool
	var finalRevision int64
	if err := withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		return tx.QueryRowContext(ctx, `SELECT tombstoned, lifecycle_revision FROM ibex_core.memories WHERE id=$1::uuid`, memoryID).Scan(&stillTombstoned, &finalRevision)
	}); err != nil {
		t.Fatalf("verify tombstone: %v", err)
	}
	if !stillTombstoned || finalRevision != 2 {
		t.Fatalf("tombstoned=%v revision=%d, want true/2", stillTombstoned, finalRevision)
	}
}

func TestMemoryLifecycleDownCleanAndGuarded(t *testing.T) {
	dsn := testDSN()
	db := openTestDB(t)
	defer db.Close()
	resetSchema(t, db)
	if err := Up(dsn); err != nil {
		t.Fatalf("up: %v", err)
	}
	if err := Down(dsn); err != nil {
		t.Fatalf("clean down of 000045: %v", err)
	}
	v, dirty, err := Version(dsn)
	if err != nil || dirty || v != 44 {
		t.Fatalf("version after clean down = (%d, dirty=%v, err=%v), want (44, false, nil)", v, dirty, err)
	}
	ctx := context.Background()
	orgA, _ := seedTwoOrgsWithAgents(t, ctx, db)
	memoryID := seedMemory(t, ctx, memorySeed{db: db, orgID: orgA, agentSlug: "agent-a", content: "lifecycle-down-guard"})
	if err := withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(ctx, `UPDATE ibex_core.memories SET status = 'deleted', deleted_at = NOW() WHERE id = $1::uuid`, memoryID)
		return err
	}); err != nil {
		t.Fatalf("create legacy deleted state: %v", err)
	}
	if err := Up(dsn); err != nil {
		t.Fatalf("up after clean down: %v", err)
	}
	var tombstoned bool
	var revision int64
	if err := withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		return tx.QueryRowContext(ctx, `SELECT tombstoned, lifecycle_revision FROM ibex_core.memories WHERE id = $1::uuid`, memoryID).Scan(&tombstoned, &revision)
	}); err != nil {
		t.Fatalf("read reconciled lifecycle state: %v", err)
	}
	if !tombstoned || revision != 1 {
		t.Fatalf("reconciled state = (tombstoned=%v, revision=%d), want (true, 1)", tombstoned, revision)
	}
	downSQL, err := migrationFiles.ReadFile("000045_memory_lifecycle.down.sql")
	if err != nil {
		t.Fatalf("read down migration: %v", err)
	}
	tx, err := db.BeginTx(ctx, nil)
	if err != nil {
		t.Fatalf("begin guarded down: %v", err)
	}
	_, err = tx.ExecContext(ctx, string(downSQL))
	if err == nil || !strings.Contains(err.Error(), "refusing destructive 000045 rollback") {
		_ = tx.Rollback()
		t.Fatalf("guarded down error = %v, want refusal", err)
	}
	_ = tx.Rollback()
	v, dirty, err = Version(dsn)
	if err != nil || dirty || v != 45 {
		t.Fatalf("version after refused down = (%d, dirty=%v, err=%v), want (45, false, nil)", v, dirty, err)
	}
}
