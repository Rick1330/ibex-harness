//go:build integration

// R05: a restore replays the forget markers and the deletion receipts.
//
// "Forget" is only durable if a database restored from a backup still refuses to
// serve the forgotten content. This test seeds a memory with a sentinel body plus
// the side records an erasure leaves behind (the lifecycle-outbox marker and the
// deletion receipt) and the idempotent create response that stored the body,
// then:
//
//  1. dumps the database *before* forget and restores it — the sentinel is back,
//     which is what makes the post-forget assertion discriminating rather than
//     vacuous;
//  2. runs the forget path as the ibex_app role: the statements
//     services/memory/app/lifecycle.py executes (tombstone, ledger scrub,
//     lifecycle-outbox marker);
//  3. dumps again and restores into a second database;
//  4. asserts the restored copy still carries the tombstone, '[forgotten]', the
//     outbox marker, the receipt's verified_absent_at, and the erased ledger
//     marker — and that the sentinel is gone.
//
// A full in-place restore would destroy the database the harness shares, so each
// restore is a second database created from a real pg_dump/pg_restore round trip:
// pg_restore renders the custom-format archive to SQL and psql applies it. The
// dump is taken with --no-owner --no-privileges so the copy depends on no
// cluster-global role grants and can be dropped without blocking the harness's
// role cleanup (roles are cluster-global; see migrate_integration_main_test.go).
//
// The apply step passes through stripCompatibilityStatement, which removes the
// one statement a newer client writes and a PostgreSQL 16 server cannot execute
// (see pgCompatStatement).
//
// Requires PostgreSQL client tools: pg_dump, pg_restore, and psql as <name>-16 or
// /usr/lib/postgresql/16/bin/*, falling back to the unversioned binaries. A newer
// client is tolerated; psql must come from the same installation as pg_restore,
// because pg_restore 17.6 and later render \restrict/\unrestrict meta-commands
// that only a matching psql understands.
package postgres

import (
	"bytes"
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"slices"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/lib/pq"
)

const (
	replaySentinel   = "restore-replay sentinel 4f8c2d unforgettable"
	replayDedupeKey  = "restore-replay-create"
	erasedMarkerText = `{"erased": true}`
)

// forgetTombstoneSQL mirrors lifecycle.py's _TOMBSTONE_SQL. The Python erasure
// suite owns forget semantics (test_lifecycle_fences.py); this test owns restore
// replay, and asserts the resulting state before dumping so a contract drift
// fails here loudly instead of passing silently.
const forgetTombstoneSQL = `
	UPDATE ibex_core.memories
	SET status = 'deleted',
	    deleted_at = COALESCE(deleted_at, NOW()),
	    tombstoned = TRUE,
	    content = '[forgotten]',
	    content_hash = md5(random()::text) || md5(random()::text),
	    content_tokens = 0,
	    metadata = '{}'::jsonb,
	    pii_detected = FALSE,
	    pii_redacted = FALSE,
	    confidence = 0.80,
	    usefulness_score = 0.50,
	    retrieval_count = 0,
	    last_retrieved_at = NULL,
	    superseded_by = NULL,
	    merged_into = NULL,
	    embedding = NULL,
	    embedding_model = NULL,
	    embedding_dim = NULL,
	    updated_at = NOW()
	WHERE id = $1::uuid
	  AND org_id = $2::uuid
	  AND agent_id = $3::uuid
	  AND lifecycle_revision = $4
	  AND tombstoned = FALSE
	RETURNING lifecycle_revision`

// forgetLedgerScrubSQL mirrors the idempotency-ledger statement in
// lifecycle.py's _ERASE_MEMORY_CHILDREN_SQL: the row survives, its body becomes
// the erased marker, matched on the created memory's id.
const forgetLedgerScrubSQL = `
	UPDATE ibex_core.idempotency_ledger
	SET response_payload = convert_to($1::text, 'UTF8')
	WHERE organization_id = $2::uuid
	  AND response_payload IS NOT NULL
	  AND pg_input_is_valid(convert_from(response_payload, 'UTF8'), 'jsonb')
	  AND (convert_from(response_payload, 'UTF8')::jsonb #>> '{data,id}') = $3`

// forgetOutboxSQL mirrors lifecycle.py's _INSERT_EVENT_SQL.
const forgetOutboxSQL = `
	INSERT INTO ibex_core.memory_lifecycle_outbox
		(org_id, memory_id, revision, schema_version, event_type, occurred_at)
	VALUES ($1::uuid, $2::uuid, $3, 1, 'forgotten', NOW())`

// replayFixture names every row the scenario seeds and asserts.
type replayFixture struct {
	orgID    string
	userID   string
	agentID  string
	memoryID string
	jobID    string
}

// TestRestoreReplaysMarkersAndReceipts is the R05 gate: a restore must replay the
// forget markers and the deletion receipt, and must not resurrect the content.
func TestRestoreReplaysMarkersAndReceipts(t *testing.T) {
	r := newRestoreReplay(t)
	defer r.close()

	r.migrate()
	fixture := r.seed()

	r.requireResurrected(r.restore("pre", r.dump("pre")), fixture)

	r.forget(fixture)
	r.requireForgottenState(r.db, fixture, "source")

	r.requireForgottenState(r.restore("post", r.dump("post")), fixture, "restored copy")
}

// restoreReplay owns the database under test, the client tools, and the scratch
// directory the dumps are written to.
type restoreReplay struct {
	t         *testing.T
	dsn       string
	conn      pgConn
	db        *sql.DB
	dir       string
	pgDump    string
	pgRestore string
	psql      string
}

// newRestoreReplay migrates a clean database and resolves the client tools.
func newRestoreReplay(t *testing.T) *restoreReplay {
	t.Helper()
	dsn := testDSN()
	db := openTestDB(t)
	resetSchema(t, db)
	return &restoreReplay{
		t:         t,
		dsn:       dsn,
		conn:      parsePGConn(t, dsn),
		db:        db,
		dir:       t.TempDir(),
		pgDump:    requirePGTool(t, "pg_dump"),
		pgRestore: requirePGTool(t, "pg_restore"),
		psql:      requirePGTool(t, "psql"),
	}
}

func (r *restoreReplay) close() { _ = r.db.Close() }

func (r *restoreReplay) migrate() {
	r.t.Helper()
	if err := Up(r.dsn); err != nil {
		r.t.Fatalf("up: %v", err)
	}
}

// requirePGTool resolves a PostgreSQL client binary or fails with the reason.
// A skip would silently disable the gate, so a missing tool is a failure. The
// versioned names come first: a client older than the server refuses to dump it,
// and the migrated image is PostgreSQL 16. psql and pg_restore resolve through
// this same list, so an installation that provides both supplies both.
func requirePGTool(t *testing.T, name string) string {
	t.Helper()
	for _, candidate := range []string{
		name + "-16",
		filepath.Join("/usr/lib/postgresql/16/bin", name),
		name,
	} {
		if path, err := exec.LookPath(candidate); err == nil {
			return path
		}
	}
	t.Fatalf("%s not found: the restore-replay gate needs the PostgreSQL client tools", name)
	return ""
}

// --- seeding ---------------------------------------------------------------

func (r *restoreReplay) seed() replayFixture {
	r.t.Helper()
	fixture := replayFixture{
		orgID:    uuid.NewString(),
		userID:   uuid.NewString(),
		agentID:  uuid.NewString(),
		memoryID: uuid.NewString(),
		jobID:    uuid.NewString(),
	}
	ctx := context.Background()
	err := withServiceAccount(ctx, r.db, func(tx *sql.Tx) error {
		return insertReplayFixture(ctx, tx, fixture)
	})
	if err != nil {
		r.t.Fatalf("seed replay fixture: %v", err)
	}
	return fixture
}

func insertReplayFixture(ctx context.Context, tx *sql.Tx, fixture replayFixture) error {
	if err := insertReplayIdentity(ctx, tx, fixture); err != nil {
		return err
	}
	if err := insertReplayMemory(ctx, tx, fixture); err != nil {
		return err
	}
	return insertReplayRecords(ctx, tx, fixture)
}

// seedStatement is one bound INSERT in a seeding transaction.
type seedStatement struct {
	query string
	args  []any
}

func insertReplayIdentity(ctx context.Context, tx *sql.Tx, f replayFixture) error {
	statements := []seedStatement{
		{
			`INSERT INTO ibex_core.organizations (id, name, slug) VALUES ($1::uuid, $2, $3)`,
			[]any{f.orgID, "Restore Replay Org", "restore-replay-" + f.orgID[:8]},
		},
		{
			`INSERT INTO ibex_core.users (id, org_id, email, name) VALUES ($1::uuid, $2::uuid, $3, $4)`,
			[]any{f.userID, f.orgID, "replay-" + f.orgID[:8] + "@example.com", "Replay User"},
		},
		{
			`INSERT INTO ibex_core.agents (id, org_id, created_by, name, slug)
			 VALUES ($1::uuid, $2::uuid, $3::uuid, $4, $5)`,
			[]any{f.agentID, f.orgID, f.userID, "Replay Agent", "replay-" + f.agentID[:8]},
		},
	}
	return execAll(ctx, tx, statements)
}

func insertReplayMemory(ctx context.Context, tx *sql.Tx, f replayFixture) error {
	// nosemgrep: go_sql_rule-concat-sqli -- test fixture: the statement is a compile-time literal and every value is a bound parameter; only the content-hash parameter concatenates an id.
	_, err := tx.ExecContext(ctx, `
		INSERT INTO ibex_core.memories
			(id, org_id, agent_id, content, content_hash, content_tokens)
		VALUES ($1::uuid, $2::uuid, $3::uuid, $4, $5, 6)`,
		f.memoryID, f.orgID, f.agentID, replaySentinel, "replay-hash-"+f.memoryID[:8])
	return err
}

// insertReplayRecords seeds the durable side records: the idempotent create whose
// body stores the content, the deletion job, and its verified receipt.
func insertReplayRecords(ctx context.Context, tx *sql.Tx, f replayFixture) error {
	payload, err := json.Marshal(map[string]any{
		"data": map[string]string{"id": f.memoryID, "content": replaySentinel},
	})
	if err != nil {
		return fmt.Errorf("marshal ledger payload: %w", err)
	}
	statements := []seedStatement{
		{
			`INSERT INTO ibex_core.idempotency_ledger
				(organization_id, agent_id, dedupe_key, request_hash, state,
				 status_code, response_payload)
			 VALUES ($1::uuid, $2::uuid, $3, $4, 'finalized', 201, convert_to($5, 'UTF8'))`,
			[]any{f.orgID, f.agentID, replayDedupeKey, strings.Repeat("a", 64), string(payload)},
		},
		{
			`INSERT INTO ibex_core.org_deletion_jobs (id, org_id, status)
			 VALUES ($1::uuid, $2::uuid, 'succeeded')`,
			[]any{f.jobID, f.orgID},
		},
		{
			`INSERT INTO ibex_core.deletion_store_receipts
				(job_id, store, status, verified_absent_at, idempotency_key)
			 VALUES ($1::uuid, 'postgres', 'verified', NOW(), $2)`,
			[]any{f.jobID, "replay-receipt"},
		},
	}
	return execAll(ctx, tx, statements)
}

func execAll(ctx context.Context, tx *sql.Tx, statements []seedStatement) error {
	for _, statement := range statements {
		// nosemgrep: go_sql_rule-concat-sqli -- test fixture: every statement is a compile-time literal from the seedStatement table; all values are bound parameters.
		if _, err := tx.ExecContext(ctx, statement.query, statement.args...); err != nil {
			return fmt.Errorf("seed statement: %w", err)
		}
	}
	return nil
}

// --- forget ----------------------------------------------------------------

// forget runs the lifecycle forget path as the tenant role, mirroring the
// production transaction: set_service_org pins ibex_app and the org GUC, then
// the tombstone, ledger scrub, and outbox marker commit together.
func (r *restoreReplay) forget(f replayFixture) {
	r.t.Helper()
	ctx := context.Background()
	tx, err := r.db.BeginTx(ctx, nil)
	if err != nil {
		r.t.Fatalf("begin forget: %v", err)
	}
	defer func() { _ = tx.Rollback() }()

	if _, err := tx.ExecContext(ctx, `SET LOCAL ROLE ibex_app`); err != nil {
		r.t.Fatalf("pin ibex_app: %v", err)
	}
	if _, err := tx.ExecContext(ctx,
		`SELECT set_config('app.current_org_id', $1, true)`, f.orgID); err != nil {
		r.t.Fatalf("pin org: %v", err)
	}
	revision, err := forgetOneMemory(ctx, tx, f)
	if err != nil {
		r.t.Fatalf("forget: %v", err)
	}
	if revision != 2 {
		r.t.Fatalf("forget revision = %d, want 2", revision)
	}
	if err := tx.Commit(); err != nil {
		r.t.Fatalf("commit forget: %v", err)
	}
}

func forgetOneMemory(ctx context.Context, tx *sql.Tx, f replayFixture) (int, error) {
	var revision int
	err := tx.QueryRowContext(ctx, forgetTombstoneSQL,
		f.memoryID, f.orgID, f.agentID, 1).Scan(&revision)
	if err != nil {
		return 0, fmt.Errorf("tombstone: %w", err)
	}
	if _, err := tx.ExecContext(ctx, forgetLedgerScrubSQL,
		erasedMarkerText, f.orgID, f.memoryID); err != nil {
		return 0, fmt.Errorf("ledger scrub: %w", err)
	}
	if _, err := tx.ExecContext(ctx, forgetOutboxSQL,
		f.orgID, f.memoryID, revision); err != nil {
		return 0, fmt.Errorf("outbox marker: %w", err)
	}
	return revision, nil
}

// --- dump and restore ------------------------------------------------------

// pgCompatStatement is the one statement a newer pg_dump writes into the archive
// header that the PostgreSQL 16 server cannot execute. PostgreSQL 17 introduced
// the transaction_timeout GUC, so pg_dump 17 and later emit
// "SET transaction_timeout = 0;" in the archive's init block; replaying such an
// archive against the PostgreSQL 16 server (pgvector/pgvector:pg16) fails with
// `unrecognized configuration parameter "transaction_timeout"`.
//
// The statement sits in the archive's init entry, which pg_restore's table of
// contents cannot address (pg_restore -l does not list it and --use-list cannot
// drop it), so the restore is applied from the SQL pg_restore renders and exactly
// this line is removed. psql runs with ON_ERROR_STOP=1, which is stricter than
// pg_restore's default of ignoring errors: every other error still fails the test.
const pgCompatStatement = "SET transaction_timeout = 0;"

func (r *restoreReplay) dump(label string) string {
	r.t.Helper()
	path := filepath.Join(r.dir, label+".dump")
	r.runPG("", r.pgDump, append(r.conn.args(),
		"--no-owner", "--no-privileges", "--format=custom",
		"--file="+path, "--dbname="+r.conn.database)...)
	return path
}

// restore creates a scratch database from dumpPath and returns its handle. The
// database is dropped with the test, after its connections are closed.
func (r *restoreReplay) restore(label, dumpPath string) *sql.DB {
	r.t.Helper()
	name := newRestoreDatabaseName(r.t, label)
	r.adminExec("CREATE DATABASE " + pq.QuoteIdentifier(name))

	db := openDatabase(r.t, dsnWithDatabase(r.t, r.dsn, name))
	r.t.Cleanup(func() {
		_ = db.Close()
		r.adminLog("DROP DATABASE IF EXISTS " + pq.QuoteIdentifier(name) + " WITH (FORCE)")
	})
	r.applyDump(name, dumpPath)
	return db
}

// applyDump renders the custom-format archive to SQL, drops the statement the
// server cannot execute, and pipes the rest to psql on standard input.
func (r *restoreReplay) applyDump(database, dumpPath string) {
	r.t.Helper()
	sql, err := r.pgRun("", r.pgRestore, "--no-owner", "--no-privileges", "--file=-", dumpPath)
	if err != nil {
		r.t.Fatalf("pg_restore render %s: %v", filepath.Base(dumpPath), err)
	}
	patched, dropped := stripCompatibilityStatement(sql)
	if dropped > 0 {
		r.t.Logf("compatibility shim: dropped %q from %s (pg_dump 17+ against a PostgreSQL 16 server)",
			pgCompatStatement, filepath.Base(dumpPath))
	}
	r.runPG(patched, r.psql, append(r.conn.args(),
		"--no-psqlrc", "--quiet", "--set=ON_ERROR_STOP=1",
		"--dbname="+database, "--file=-")...)
}

// stripCompatibilityStatement removes pgCompatStatement from the SQL pg_restore
// renders and returns the remainder with the number of lines dropped. Only an
// exact whole-line match is dropped, so a different SET, a reformatted statement,
// or any other failure is left for psql to stop on.
func stripCompatibilityStatement(sql string) (string, int) {
	lines := strings.Split(sql, "\n")
	kept := make([]string, 0, len(lines))
	dropped := 0
	for _, line := range lines {
		if strings.TrimSuffix(line, "\r") == pgCompatStatement {
			dropped++
			continue
		}
		kept = append(kept, line)
	}
	return strings.Join(kept, "\n"), dropped
}

// TestStripCompatibilityStatementDropsOnlyTheKnownStatement is a unit test (it
// opens no database): the shim must remove exactly one statement and leave every
// other SET, and every other line, for psql to execute or fail on.
func TestStripCompatibilityStatementDropsOnlyTheKnownStatement(t *testing.T) {
	skewed := "SET statement_timeout = 0;\n" + pgCompatStatement + "\nSET lock_timeout = 0;\n"
	got, dropped := stripCompatibilityStatement(skewed)
	if dropped != 1 {
		t.Fatalf("dropped %d statements, want 1", dropped)
	}
	want := "SET statement_timeout = 0;\nSET lock_timeout = 0;\n"
	if got != want {
		t.Fatalf("stripped script = %q, want %q", got, want)
	}

	clean := "SET lock_timeout = 0;\n"
	if got, dropped := stripCompatibilityStatement(clean); dropped != 0 || got != clean {
		t.Fatalf("clean script = %q (dropped %d), want it unchanged", got, dropped)
	}
}

// restoreDatabasePattern is the exact shape of the scratch database name this
// file generates: the fixed ibex_restore_ prefix, a scenario label, and eight hex
// characters from a UUID. The client tools and the DDL only ever receive an
// identifier that matches it.
var restoreDatabasePattern = regexp.MustCompile(`^ibex_restore_[a-z]+_[0-9a-f]{8}$`)

// newRestoreDatabaseName generates the scratch database name and refuses to hand
// out anything outside restoreDatabasePattern.
func newRestoreDatabaseName(t *testing.T, label string) string {
	t.Helper()
	name := "ibex_restore_" + label + "_" + strings.ReplaceAll(uuid.NewString(), "-", "")[:8]
	if !restoreDatabasePattern.MatchString(name) {
		t.Fatalf("generated database name %q does not match %s", name, restoreDatabasePattern)
	}
	return name
}

// runPG executes a client tool and fails the test on a non-zero exit.
func (r *restoreReplay) runPG(stdin string, binary string, args ...string) {
	r.t.Helper()
	if _, err := r.pgRun(stdin, binary, args...); err != nil {
		r.t.Fatalf("%s failed: %v", filepath.Base(binary), err)
	}
}

// pgRun executes a client tool with the connection arguments and the DSN's
// secrets in the environment, so no credential appears in argv, and returns its
// standard output.
func (r *restoreReplay) pgRun(stdin string, binary string, args ...string) (string, error) {
	r.requireSafeDatabaseArgs(args)
	// nosemgrep: go.lang.security.audit.dangerous-exec-command.dangerous-exec-command, go_subproc_rule-subproc -- test harness: binary is one of the fixed PostgreSQL client paths requirePGTool resolved with exec.LookPath over a literal candidate list, and the only argument that is not a fixed flag or a temp-file path is a --dbname validated by requireSafeDatabaseArgs.
	cmd := exec.Command(binary, args...)
	cmd.Env = r.conn.env()
	if stdin != "" {
		cmd.Stdin = strings.NewReader(stdin)
	}
	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr
	if err := cmd.Run(); err != nil {
		return stdout.String(), fmt.Errorf("%w\n%s", err, stderr.String())
	}
	return stdout.String(), nil
}

// requireSafeDatabaseArgs fails the test if a client-tool argument names a
// database this file did not generate. --dbname is the only argument carrying a
// database identifier; the rest are fixed flags or paths inside the test's
// temporary directory.
func (r *restoreReplay) requireSafeDatabaseArgs(args []string) {
	for _, arg := range args {
		value, ok := strings.CutPrefix(arg, "--dbname=")
		if !ok || r.acceptsDatabase(value) {
			continue
		}
		r.t.Fatalf("refusing client tool database %q: not the configured database and not %s",
			value, restoreDatabasePattern)
	}
}

// acceptsDatabase reports whether a client tool may name this database: the
// configured database the dump is taken from, or a scratch database this file
// generated.
func (r *restoreReplay) acceptsDatabase(name string) bool {
	return name == r.conn.database || restoreDatabasePattern.MatchString(name)
}

func (r *restoreReplay) adminExec(statement string) {
	r.t.Helper()
	if err := r.adminRun(statement); err != nil {
		r.t.Fatalf("%s: %v", statement, err)
	}
}

func (r *restoreReplay) adminLog(statement string) {
	if err := r.adminRun(statement); err != nil {
		r.t.Logf("%s: %v", statement, err)
	}
}

func (r *restoreReplay) adminRun(statement string) error {
	db := openDatabase(r.t, dsnWithDatabase(r.t, r.dsn, "postgres"))
	defer func() { _ = db.Close() }()
	// nosemgrep: go_sql_rule-concat-sqli -- test fixture DDL: the only interpolated identifier is a quoted database name that newRestoreDatabaseName validated against restoreDatabasePattern.
	_, err := db.ExecContext(context.Background(), statement)
	return err
}

// --- assertions ------------------------------------------------------------

// requireResurrected proves the assertion discriminates: a restore of the
// pre-forget database serves the sentinel content again.
func (r *restoreReplay) requireResurrected(db *sql.DB, f replayFixture) {
	r.t.Helper()
	memory := readMemory(r.t, db, f)
	if !memory.isResurrected() {
		r.t.Fatalf("pre-forget restore did not resurrect the content: %+v", memory)
	}
	r.t.Logf("discriminator: pre-forget restore resurrects content=%q tombstoned=%v status=%q",
		memory.content, memory.tombstoned, memory.status)
	if payload := readLedgerPayload(r.t, db, f); !strings.Contains(payload, replaySentinel) {
		r.t.Fatalf("pre-forget restore lost the create response: %q", payload)
	}
}

// requireForgottenState asserts the tombstone, the outbox marker, the receipt,
// and the erased ledger payload. It runs against the source database (so a broken
// forget is reported as a forget failure, not a restore one) and against the
// restored copy (so a restore that drops a marker is reported as a restore
// failure). where names which copy failed.
func (r *restoreReplay) requireForgottenState(db *sql.DB, f replayFixture, where string) {
	r.t.Helper()
	memory := readMemory(r.t, db, f)
	if !memory.isTombstone() {
		r.t.Fatalf("%s: memory is not a tombstone: %+v", where, memory)
	}
	r.t.Logf("%s: content=%q tombstoned=%v status=%q", where,
		memory.content, memory.tombstoned, memory.status)
	requireOutboxMarker(r.t, db, f, where)
	requireReceipt(r.t, db, f, where)
	payload := readLedgerPayload(r.t, db, f)
	if payload != erasedMarkerText {
		r.t.Fatalf("%s: ledger payload = %q, want %q", where, payload, erasedMarkerText)
	}
}

type replayMemory struct {
	content    string
	status     string
	tombstoned bool
}

// isResurrected is the pre-forget state a stale restore must reproduce.
func (m replayMemory) isResurrected() bool {
	return m.content == replaySentinel && m.status == "active" && !m.tombstoned
}

// isTombstone is the post-forget state every restore must reproduce.
func (m replayMemory) isTombstone() bool {
	return m.content == "[forgotten]" && m.status == "deleted" && m.tombstoned
}

func readMemory(t *testing.T, db *sql.DB, f replayFixture) replayMemory {
	t.Helper()
	var memory replayMemory
	err := db.QueryRowContext(context.Background(), `
		SELECT content, status, tombstoned FROM ibex_core.memories
		WHERE id = $1::uuid AND org_id = $2::uuid`, f.memoryID, f.orgID,
	).Scan(&memory.content, &memory.status, &memory.tombstoned)
	if err != nil {
		t.Fatalf("read memory: %v", err)
	}
	return memory
}

func requireOutboxMarker(t *testing.T, db *sql.DB, f replayFixture, where string) {
	t.Helper()
	rows, err := db.QueryContext(context.Background(), `
		SELECT event_type, revision FROM ibex_core.memory_lifecycle_outbox
		WHERE org_id = $1::uuid AND memory_id = $2::uuid`, f.orgID, f.memoryID)
	if err != nil {
		t.Fatalf("read outbox: %v", err)
	}
	defer func() { _ = rows.Close() }()

	var events []string
	for rows.Next() {
		var event string
		var revision int
		if err := rows.Scan(&event, &revision); err != nil {
			t.Fatalf("scan outbox: %v", err)
		}
		events = append(events, fmt.Sprintf("%s/%d", event, revision))
	}
	if len(events) != 1 || events[0] != "forgotten/2" {
		t.Fatalf("%s: lifecycle outbox markers = %v, want [forgotten/2]", where, events)
	}
}

func requireReceipt(t *testing.T, db *sql.DB, f replayFixture, where string) {
	t.Helper()
	var verifiedAt sql.NullTime
	err := db.QueryRowContext(context.Background(), `
		SELECT verified_absent_at FROM ibex_core.deletion_store_receipts
		WHERE job_id = $1::uuid AND store = 'postgres'`, f.jobID).Scan(&verifiedAt)
	if err != nil {
		t.Fatalf("read deletion receipt: %v", err)
	}
	if !verifiedAt.Valid {
		t.Fatalf("%s: deletion receipt has verified_absent_at = NULL", where)
	}
}

func readLedgerPayload(t *testing.T, db *sql.DB, f replayFixture) string {
	t.Helper()
	var payload string
	err := db.QueryRowContext(context.Background(), `
		SELECT convert_from(response_payload, 'UTF8') FROM ibex_core.idempotency_ledger
		WHERE organization_id = $1::uuid AND dedupe_key = $2`,
		f.orgID, replayDedupeKey).Scan(&payload)
	if err != nil {
		t.Fatalf("read ledger payload: %v", err)
	}
	return payload
}

// --- connection helpers ----------------------------------------------------

// pgConn is the connection a client tool needs, kept separate from the DSN so
// the password and the TLS key locations travel in the environment rather than in
// argv.
type pgConn struct {
	host        string
	port        string
	user        string
	password    string
	database    string
	sslcert     string
	sslkey      string
	sslrootcert string
}

func parsePGConn(t *testing.T, dsn string) pgConn {
	t.Helper()
	parsed, err := url.Parse(dsn)
	if err != nil || parsed.Scheme == "" {
		t.Fatalf("parse dsn %s: %v", RedactedDSN(dsn), err)
	}
	query := parsed.Query()
	conn := pgConn{
		host:        parsed.Hostname(),
		port:        parsed.Port(),
		database:    strings.TrimPrefix(parsed.Path, "/"),
		sslcert:     query.Get("sslcert"),
		sslkey:      query.Get("sslkey"),
		sslrootcert: query.Get("sslrootcert"),
	}
	if parsed.User != nil {
		conn.user = parsed.User.Username()
		conn.password, _ = parsed.User.Password()
	}
	return conn
}

func (c pgConn) args() []string {
	var args []string
	if c.host != "" {
		args = append(args, "-h", c.host)
	}
	if c.port != "" {
		args = append(args, "-p", c.port)
	}
	if c.user != "" {
		args = append(args, "-U", c.user)
	}
	return args
}

// env is the client-tool environment: the inherited environment plus the DSN's
// password and TLS file locations, which libpq reads as PGSSLCERT, PGSSLKEY, and
// PGSSLROOTCERT. They travel here so no credential and no key path reaches argv.
func (c pgConn) env() []string {
	env := os.Environ()
	for _, pair := range [][2]string{
		{"PGPASSWORD", c.password},
		{"PGSSLCERT", c.sslcert},
		{"PGSSLKEY", c.sslkey},
		{"PGSSLROOTCERT", c.sslrootcert},
	} {
		if pair[1] != "" {
			env = append(env, pair[0]+"="+pair[1])
		}
	}
	return env
}

// tlsProbeDSN is a synthetic DSN: no real host, no real credential. It exists to
// prove parsePGConn carries the TLS file options into the client environment and
// keeps the credential out of argv.
const tlsProbeDSN = "postgres://ibex:probe-credential@db.example.internal:5433/ibex" +
	"?sslmode=verify-full" +
	"&sslcert=%2Fetc%2Fibex%2Fclient.crt" +
	"&sslkey=%2Fetc%2Fibex%2Fclient.key" +
	"&sslrootcert=%2Fetc%2Fibex%2Fca.crt"

// TestParsePGConnRetainsTLSOptions is a unit test (it opens no database): the
// client tools must receive the DSN's TLS file locations through libpq's PGSSL*
// variables, and the DSN's credential must never reach argv.
func TestParsePGConnRetainsTLSOptions(t *testing.T) {
	conn := parsePGConn(t, tlsProbeDSN)
	requireTLSOptions(t, conn)
	requireClientEnv(t, conn.env())
	requireNoCredentialInArgv(t, conn.args())
}

func requireTLSOptions(t *testing.T, conn pgConn) {
	t.Helper()
	if conn.sslcert != "/etc/ibex/client.crt" {
		t.Fatalf("sslcert = %q, want %q", conn.sslcert, "/etc/ibex/client.crt")
	}
	if conn.sslkey != "/etc/ibex/client.key" {
		t.Fatalf("sslkey = %q, want %q", conn.sslkey, "/etc/ibex/client.key")
	}
	if conn.sslrootcert != "/etc/ibex/ca.crt" {
		t.Fatalf("sslrootcert = %q, want %q", conn.sslrootcert, "/etc/ibex/ca.crt")
	}
}

// requireClientEnv asserts the libpq variables a client tool inherits, so the
// TLS files and the credential reach pg_dump, pg_restore, and psql.
func requireClientEnv(t *testing.T, env []string) {
	t.Helper()
	for _, want := range []string{
		"PGPASSWORD=probe-credential",
		"PGSSLCERT=/etc/ibex/client.crt",
		"PGSSLKEY=/etc/ibex/client.key",
		"PGSSLROOTCERT=/etc/ibex/ca.crt",
	} {
		if !slices.Contains(env, want) {
			t.Fatalf("client environment is missing %s", want)
		}
	}
}

// requireNoCredentialInArgv asserts the process command line carries neither the
// credential nor a TLS key path.
func requireNoCredentialInArgv(t *testing.T, argv []string) {
	t.Helper()
	for _, arg := range argv {
		if strings.Contains(arg, "probe-credential") {
			t.Fatalf("argv carries the DSN credential")
		}
		if strings.Contains(arg, "/etc/ibex/") {
			t.Fatalf("argv carries a TLS path: %q", arg)
		}
	}
}

// dsnWithDatabase points the configured DSN at another database on the same
// cluster. The harness only ever holds the URL form (see RedactedDSN).
func dsnWithDatabase(t *testing.T, dsn, database string) string {
	t.Helper()
	parsed, err := url.Parse(dsn)
	if err != nil || parsed.Scheme == "" {
		t.Fatalf("parse dsn %s: %v", RedactedDSN(dsn), err)
	}
	parsed.Path = "/" + database
	return parsed.String()
}

func openDatabase(t *testing.T, dsn string) *sql.DB {
	t.Helper()
	db, err := sql.Open("postgres", dsn)
	if err != nil {
		t.Fatalf("open %s: %v", RedactedDSN(dsn), err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	if err := db.PingContext(ctx); err != nil {
		_ = db.Close()
		t.Fatalf("ping %s: %v", RedactedDSN(dsn), err)
	}
	return db
}
