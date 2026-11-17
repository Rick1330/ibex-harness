package bootstrap

import (
	"context"
	"database/sql"
	"database/sql/driver"
	"errors"
	"io"
	"path/filepath"
	"testing"

	"github.com/Rick1330/ibex-harness/services/auth/internal/token"
	"github.com/google/uuid"
)

// This file is the fault-injection harness the bootstrap fault tests share: the
// driver that fails a chosen database boundary, the configuration a test sets to
// choose which boundary, and the row fixtures that answer the queries before it.
// The tests themselves live in the sibling files, grouped by the function each
// one proves, so a failure names the concern it belongs to.

// The fault driver injects failures at each database boundary. It exists so the
// defensive error returns in bootstrap.go are exercised deterministically: a
// real server cannot be made to fail a single Exec or Commit on demand, and
// mocking the code under test would not prove anything.
var errInjected = errors.New("injected database fault")

// faultRow is the one row the nth query returns. Queries past the end of
// faultConfig.rows return no rows, so a test can satisfy a SELECT and then make
// a later one come back empty.
type faultRow struct {
	columns []string
	values  []driver.Value
	// noRows makes the query return an empty result set. A row with no values is
	// not the same thing: the driver would hand the destination an unwritten
	// slot and the Scan would fail.
	noRows bool
}

type faultConfig struct {
	begin  error
	exec   error
	query  error
	ping   error
	commit error
	// execAfter and queryAfter are the number of successful calls before the
	// configured error fires, so a test can reach the second or third statement
	// of an orchestrator.
	execAfter  int
	queryAfter int
	// rows holds the result of each query in order.
	rows []faultRow
	// scan writes a value the destination cannot accept.
	scan bool
}

var (
	fault      faultConfig
	execCalls  int
	queryCalls int
)

func init() { sql.Register("ibex-fault", faultDriver{}) }

type faultDriver struct{}

func (faultDriver) Open(string) (driver.Conn, error) { return faultConn{}, nil }

type faultConn struct{}

func (faultConn) Prepare(string) (driver.Stmt, error) { return nil, errInjected }

func (faultConn) Close() error { return nil }

func (faultConn) Begin() (driver.Tx, error) { return faultTx{}, nil }

func (faultConn) BeginTx(context.Context, driver.TxOptions) (driver.Tx, error) {
	if fault.begin != nil {
		return nil, fault.begin
	}
	return faultTx{}, nil
}

type faultTx struct{}

func (faultTx) Commit() error   { return fault.commit }
func (faultTx) Rollback() error { return nil }

func (faultConn) Ping(context.Context) error { return fault.ping }

func (faultConn) ExecContext(context.Context, string, []driver.NamedValue) (driver.Result, error) {
	execCalls++
	if fault.exec != nil && execCalls > fault.execAfter {
		return nil, fault.exec
	}
	return faultResult{}, nil
}

func (faultConn) QueryContext(context.Context, string, []driver.NamedValue) (driver.Rows, error) {
	queryCalls++
	if fault.query != nil && queryCalls > fault.queryAfter {
		return nil, fault.query
	}
	return &faultRows{index: queryCalls}, nil
}

type faultResult struct{}

func (faultResult) LastInsertId() (int64, error) { return 0, nil }
func (faultResult) RowsAffected() (int64, error) { return 0, nil }

type faultRows struct {
	// index is the 1-based query number this result belongs to.
	index int
	sent  bool
}

func (r *faultRows) Columns() []string {
	if row, ok := fault.rowAt(r.index); ok {
		return row.columns
	}
	return []string{"id"}
}

func (r *faultRows) Close() error { return nil }

func (r *faultRows) Next(dest []driver.Value) error {
	if r.sent {
		return io.EOF
	}
	if fault.scan {
		r.sent = true
		dest[0] = "not-a-uuid"
		return nil
	}
	row, ok := fault.rowAt(r.index)
	if !ok || row.noRows {
		return io.EOF
	}
	r.sent = true
	copy(dest, row.values)
	return nil
}

// rowAt returns the configured row for a 1-based query number.
func (f faultConfig) rowAt(query int) (faultRow, bool) {
	if query < 1 || query > len(f.rows) {
		return faultRow{}, false
	}
	return f.rows[query-1], true
}

// openFaultDB returns a handle backed by the fault driver. The cleanup restores
// the zero configuration so one test cannot leak a fault into another.
func openFaultDB(t *testing.T, cfg faultConfig) *sql.DB {
	t.Helper()
	fault = cfg
	execCalls = 0
	queryCalls = 0
	t.Cleanup(func() {
		fault = faultConfig{}
		execCalls = 0
		queryCalls = 0
	})

	db, err := sql.Open("ibex-fault", "")
	if err != nil {
		t.Fatalf("open fault db: %v", err)
	}
	t.Cleanup(func() { _ = db.Close() })
	return db
}

// testConfig is a valid configuration; the SQL helpers under test never reach
// the network with the fault driver.
func testConfig(t *testing.T) bootstrapConfig {
	t.Helper()
	return bootstrapConfig{
		PostgresDSN: "postgres://ibex:ibex@localhost:5432/ibex?sslmode=disable",
		OrgName:     "Fault Injection",
		OrgSlug:     "fault-injection",
		UserEmail:   "owner@example.com",
		UserName:    "Owner",
		AgentName:   "Default Agent",
		AgentSlug:   "default",
		PATName:     "Bootstrap PAT",
		PATFile:     filepath.Join(t.TempDir(), "bootstrap.pat"),
		MemoryToken: mustPAT(t),
	}
}

func mustPAT(t *testing.T) string {
	t.Helper()
	pat, _, _, err := token.GeneratePAT()
	if err != nil {
		t.Fatalf("generate PAT: %v", err)
	}
	return pat
}

func beginFaultTx(t *testing.T, db *sql.DB) *sql.Tx {
	t.Helper()
	tx, err := db.BeginTx(context.Background(), nil)
	if err != nil {
		t.Fatalf("begin fault transaction: %v", err)
	}
	t.Cleanup(func() { _ = tx.Rollback() })
	return tx
}

// firstRunRows is the row set a clean first-run bootstrap reads: no existing
// organization (the second-org guard), the new organization, the identity, and
// the memory-service outcome.
func firstRunRows() []faultRow {
	return append([]faultRow{emptyInventoryRow()}, firstRunCreationRows()...)
}

// firstRunCreationRows is firstRunRows without the inventory read, for the
// helpers that start after the guard.
func firstRunCreationRows() []faultRow {
	return []faultRow{
		organizationRow(true, nil),
		identityRow(),
		serviceTokenRow(outcomeInserted, uuid.NewString()),
	}
}

// emptyInventoryRow is a bootstrap_list_org_slugs result with no organization:
// the fresh-installation case the guard must allow.
func emptyInventoryRow() faultRow {
	return faultRow{columns: []string{"slug"}, noRows: true}
}

// inventoryRow is a bootstrap_list_org_slugs result naming existing slugs.
func inventoryRow(slugs ...string) faultRow {
	values := make([]driver.Value, 0, len(slugs))
	for _, slug := range slugs {
		values = append(values, slug)
	}
	return faultRow{columns: []string{"slug"}, values: values}
}

// organizationRow is the bootstrap_upsert_organization result for a newly
// generated organization id.
func organizationRow(created bool, deletedAt driver.Value) faultRow {
	return organizationRowFor(created, uuid.New(), deletedAt)
}

// organizationRowFor is organizationRow with a caller-chosen id, so a test can
// assert which organization the upsert reported back.
func organizationRowFor(created bool, orgID uuid.UUID, deletedAt driver.Value) faultRow {
	return faultRow{
		columns: []string{"created", "org_id", "deleted_at"},
		values:  []driver.Value{created, orgID.String(), deletedAt},
	}
}

// identityRow is the bootstrap_create_identity result.
func identityRow() faultRow {
	return faultRow{
		columns: []string{"user_id", "agent_id"},
		values:  []driver.Value{uuid.NewString(), uuid.NewString()},
	}
}

// subjectsRow is the bootstrap_lookup_subjects result. A nil id is the absent
// owner or agent.
func subjectsRow(owner, agent driver.Value) faultRow {
	return faultRow{
		columns: []string{"owner_id", "agent_id"},
		values:  []driver.Value{owner, agent},
	}
}

// lockRow is the bootstrap_lock_organization result.
func lockRow(locked bool) faultRow {
	return faultRow{
		columns: []string{"bootstrap_lock_organization"},
		values:  []driver.Value{locked},
	}
}

// serviceTokenRow is the bootstrap_upsert_service_token result.
func serviceTokenRow(outcome, tokenID string) faultRow {
	var id driver.Value
	if tokenID != "" {
		id = tokenID
	}
	return faultRow{
		columns: []string{"outcome", "token_id"},
		values:  []driver.Value{outcome, id},
	}
}
