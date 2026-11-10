package repository_test

// These tests reach the transaction-lifecycle failure branches without a
// database. A scripted database/sql/driver answers each BeginTx, ExecContext,
// QueryContext and Commit from a per-test plan, so the pin and tenant-context
// statements can fail on purpose. The assertions check the error *contract*
// ({errors.Is} identity plus the wrapping context) rather than "an error was
// returned", because those branches decide whether a pin failure surfaces as a
// distinguishable error or is mistaken for a tenant miss.

import (
	"context"
	"database/sql"
	"database/sql/driver"
	"errors"
	"fmt"
	"io"
	"strings"
	"sync"
	"testing"

	"github.com/Rick1330/ibex-harness/services/auth/internal/repository"
	"github.com/google/uuid"
)

const faultDriverName = "ibex-auth-fault"

// errFault is the sentinel every injected fault returns. Tests assert it with
// errors.Is, which only passes when the repository wraps with %w.
var errFault = errors.New("injected driver fault")

// faultExecRule injects err from ExecContext when the statement contains match.
type faultExecRule struct {
	match string
	err   error
}

// faultStmt is one statement the repository issued, with its bound arguments.
type faultStmt struct {
	query string
	args  []driver.Value
}

// faultPlan is the script for one database handle. It is safe for concurrent
// use because database/sql may open more than one connection for the same DSN.
type faultPlan struct {
	beginErr              error
	commitErr             error
	execRules             []faultExecRule
	returnFirstArgOnQuery bool

	mu    sync.Mutex
	stmts []faultStmt
}

func (p *faultPlan) record(query string, args []driver.NamedValue) {
	p.mu.Lock()
	defer p.mu.Unlock()
	values := make([]driver.Value, len(args))
	for i, arg := range args {
		values[i] = arg.Value
	}
	p.stmts = append(p.stmts, faultStmt{query: query, args: values})
}

func (p *faultPlan) snapshot() []faultStmt {
	p.mu.Lock()
	defer p.mu.Unlock()
	return append([]faultStmt(nil), p.stmts...)
}

func (p *faultPlan) execErr(query string) error {
	for _, rule := range p.execRules {
		if strings.Contains(query, rule.match) {
			return rule.err
		}
	}
	return nil
}

var (
	faultPlans   sync.Map // DSN -> *faultPlan
	faultOnce    sync.Once
	faultSeq     int64
	faultSeqLock sync.Mutex
)

// openFaultDB registers the scripted driver once per process and returns a
// pool bound to plan. Each test gets a unique DSN so its plan cannot be shared.
func openFaultDB(t *testing.T, plan *faultPlan) *sql.DB {
	t.Helper()
	faultOnce.Do(func() { sql.Register(faultDriverName, faultDriver{}) })
	faultSeqLock.Lock()
	faultSeq++
	dsn := fmt.Sprintf("fault-plan-%d", faultSeq)
	faultSeqLock.Unlock()
	faultPlans.Store(dsn, plan)
	db, err := sql.Open(faultDriverName, dsn)
	if err != nil {
		t.Fatalf("open fault db: %v", err)
	}
	t.Cleanup(func() {
		_ = db.Close()
		faultPlans.Delete(dsn)
	})
	return db
}

type faultDriver struct{}

func (faultDriver) Open(name string) (driver.Conn, error) {
	value, ok := faultPlans.Load(name)
	if !ok {
		return nil, fmt.Errorf("no fault plan for %q", name)
	}
	return &faultConn{plan: value.(*faultPlan)}, nil
}

type faultConn struct{ plan *faultPlan }

func (c *faultConn) Prepare(string) (driver.Stmt, error) { return nil, driver.ErrSkip }
func (c *faultConn) Close() error                        { return nil }
func (c *faultConn) Begin() (driver.Tx, error)           { return c.begin() }

func (c *faultConn) BeginTx(context.Context, driver.TxOptions) (driver.Tx, error) {
	return c.begin()
}

func (c *faultConn) begin() (driver.Tx, error) {
	if c.plan.beginErr != nil {
		return nil, c.plan.beginErr
	}
	return &faultTx{plan: c.plan}, nil
}

func (c *faultConn) ExecContext(_ context.Context, query string, args []driver.NamedValue) (driver.Result, error) {
	c.plan.record(query, args)
	if err := c.plan.execErr(query); err != nil {
		return nil, err
	}
	return driver.RowsAffected(1), nil
}

func (c *faultConn) QueryContext(_ context.Context, query string, args []driver.NamedValue) (driver.Rows, error) {
	c.plan.record(query, args)
	if err := c.plan.execErr(query); err != nil {
		return nil, err
	}
	if c.plan.returnFirstArgOnQuery && len(args) > 0 {
		id, _ := args[0].Value.(string)
		return &faultRows{columns: []string{"id"}, data: [][]driver.Value{{id}}}, nil
	}
	return &faultRows{columns: []string{"id"}}, nil
}

type faultTx struct{ plan *faultPlan }

func (t *faultTx) Commit() error   { return t.plan.commitErr }
func (t *faultTx) Rollback() error { return nil }

type faultRows struct {
	columns []string
	data    [][]driver.Value
	next    int
}

func (r *faultRows) Columns() []string { return r.columns }
func (r *faultRows) Close() error      { return nil }

func (r *faultRows) Next(dest []driver.Value) error {
	if r.next >= len(r.data) {
		return io.EOF
	}
	copy(dest, r.data[r.next])
	r.next++
	return nil
}

// createTokenParams is a valid tenant-scoped write; only the driver is faulted.
func createTokenParams(orgID string) repository.CreateTokenParams {
	return repository.CreateTokenParams{
		ID: uuid.NewString(), OrgID: orgID, Name: "fault",
		Hash: "hash", Prefix: "ibex_pat_" + uuid.NewString(), Permissions: 1,
	}
}

// assertFaultError proves the error wraps sentinel, carries the branch context,
// and cannot be mistaken for a tenant miss or an invalid-tenant programming
// error. Any of those conflations would change how the validator/proxy respond.
func assertFaultError(t *testing.T, err, sentinel error, wantContext string) {
	t.Helper()
	if err == nil {
		t.Fatalf("expected %q error, got nil", wantContext)
	}
	if !errors.Is(err, sentinel) {
		t.Fatalf("error %v does not wrap injected fault %v", err, sentinel)
	}
	if !strings.Contains(err.Error(), wantContext) {
		t.Fatalf("error %q lost branch context %q", err.Error(), wantContext)
	}
	for _, forbidden := range []error{repository.ErrNotFound, repository.ErrInvalidTenantID, sql.ErrNoRows} {
		if errors.Is(err, forbidden) {
			t.Fatalf("error %v masquerades as %v", err, forbidden)
		}
	}
}

func assertSingleStatement(t *testing.T, stmts []faultStmt) faultStmt {
	t.Helper()
	if len(stmts) != 1 {
		t.Fatalf("issued %d statements, want exactly 1 (fail fast): %+v", len(stmts), stmts)
	}
	return stmts[0]
}

func assertNoStatementContains(t *testing.T, stmts []faultStmt, fragment string) {
	t.Helper()
	for _, stmt := range stmts {
		if strings.Contains(stmt.query, fragment) {
			t.Fatalf("statement %q ran after an earlier branch failed", stmt.query)
		}
	}
}

// TestUnit_CreateToken_PinRoleFault fails SET LOCAL ROLE. The public write must
// return a wrapped, distinguishable error and must not attempt set_config or the
// insert after the pin fails.
//
// Mutation that breaks it: ignoring the pin error, wrapping with %v, mapping the
// error to ErrNotFound, or continuing to the next statement.
func TestUnit_CreateToken_PinRoleFault(t *testing.T) {
	plan := &faultPlan{execRules: []faultExecRule{{match: "SET LOCAL ROLE ibex_app", err: errFault}}}
	repo := repository.RequireTokensRepository(t, openFaultDB(t, plan), nil)

	id, err := repo.CreateToken(context.Background(), createTokenParams(uuid.NewString()))
	if id != "" {
		t.Fatalf("failed create returned id %q", id)
	}
	assertFaultError(t, err, errFault, "pin ibex_app")

	stmts := plan.snapshot()
	stmt := assertSingleStatement(t, stmts)
	if !strings.Contains(stmt.query, "SET LOCAL ROLE ibex_app") {
		t.Fatalf("first statement = %q, want the role pin", stmt.query)
	}
	assertNoStatementContains(t, stmts, "set_config")
	assertNoStatementContains(t, stmts, "INSERT INTO ibex_core.tokens")
}

// TestUnit_CreateToken_SetOrgContextFault fails the tenant GUC. The write must
// report "set org context" (not the pin) and must not run the insert.
//
// Mutation that breaks it: ignoring set_config's error, reusing the pin's
// message, or running the caller's statement anyway.
func TestUnit_CreateToken_SetOrgContextFault(t *testing.T) {
	plan := &faultPlan{execRules: []faultExecRule{{match: "set_config", err: errFault}}}
	repo := repository.RequireTokensRepository(t, openFaultDB(t, plan), nil)

	id, err := repo.CreateToken(context.Background(), createTokenParams(uuid.NewString()))
	if id != "" {
		t.Fatalf("failed create returned id %q", id)
	}
	assertFaultError(t, err, errFault, "set org context")

	stmts := plan.snapshot()
	if len(stmts) != 2 {
		t.Fatalf("issued %d statements, want pin + set_config: %+v", len(stmts), stmts)
	}
	if !strings.Contains(stmts[0].query, "SET LOCAL ROLE ibex_app") {
		t.Fatalf("first statement = %q, want the role pin", stmts[0].query)
	}
	if !strings.Contains(stmts[1].query, "set_config") {
		t.Fatalf("second statement = %q, want set_config", stmts[1].query)
	}
	assertNoStatementContains(t, stmts, "INSERT INTO ibex_core.tokens")
}

// TestUnit_CreateToken_BeginFault proves a failed BEGIN is reported as
// "begin tx" and is not confused with a tenant miss. It also shows no SQL is
// attempted when the transaction never starts.
//
// Mutation that breaks it: wrapping the begin error without the "begin tx"
// context, dropping it, or attempting SQL without a transaction.
func TestUnit_CreateToken_BeginFault(t *testing.T) {
	plan := &faultPlan{beginErr: errFault}
	repo := repository.RequireTokensRepository(t, openFaultDB(t, plan), nil)

	id, err := repo.CreateToken(context.Background(), createTokenParams(uuid.NewString()))
	if id != "" {
		t.Fatalf("failed create returned id %q", id)
	}
	assertFaultError(t, err, errFault, "begin tx")
	if stmts := plan.snapshot(); len(stmts) != 0 {
		t.Fatalf("ran %d statements without a transaction: %+v", len(stmts), stmts)
	}
}

// TestUnit_CreateToken_CommitFault proves a failed COMMIT is surfaced to the
// caller instead of being reported as a successful write. The scanned id may be
// non-empty; the caller's only reliable signal is the returned error.
//
// Mutation that breaks it: ignoring Commit's error and returning nil, which
// would let the caller believe a rolled-back row exists.
func TestUnit_CreateToken_CommitFault(t *testing.T) {
	plan := &faultPlan{commitErr: errFault, returnFirstArgOnQuery: true}
	repo := repository.RequireTokensRepository(t, openFaultDB(t, plan), nil)

	_, err := repo.CreateToken(context.Background(), createTokenParams(uuid.NewString()))
	assertFaultError(t, err, errFault, "injected driver fault")
}

// TestUnit_InsertTestOrganization_PinsTheRowItInserts proves the helper pins
// app.current_org_id to the generated id it inserts, and returns that same id.
// A mismatch would create an organisation outside its own tenant scope or
// return an id the caller cannot find.
//
// Mutation that breaks it: pinning a different UUID than the inserted one,
// returning the input name/slug instead of the scanned id, or skipping the pin.
func TestUnit_InsertTestOrganization_PinsTheRowItInserts(t *testing.T) {
	plan := &faultPlan{returnFirstArgOnQuery: true}
	repo := repository.RequireTokensRepository(t, openFaultDB(t, plan), nil)

	id, err := repo.InsertTestOrganization(context.Background(), "Fault Org", "fault-org")
	if err != nil {
		t.Fatalf("InsertTestOrganization: %v", err)
	}
	parsed, parseErr := uuid.Parse(id)
	if parseErr != nil || parsed == uuid.Nil {
		t.Fatalf("returned id %q is not a usable uuid: %v", id, parseErr)
	}

	var pinned, inserted string
	for _, stmt := range plan.snapshot() {
		switch {
		case strings.Contains(stmt.query, "set_config"):
			if len(stmt.args) != 1 {
				t.Fatalf("set_config args = %v", stmt.args)
			}
			pinned, _ = stmt.args[0].(string)
		case strings.Contains(stmt.query, "INSERT INTO ibex_core.organizations"):
			if len(stmt.args) != 3 {
				t.Fatalf("insert args = %v", stmt.args)
			}
			inserted, _ = stmt.args[0].(string)
			if stmt.args[1] != "Fault Org" || stmt.args[2] != "fault-org" {
				t.Fatalf("insert args = %v, want name/slug preserved", stmt.args)
			}
		}
	}
	if inserted != id {
		t.Fatalf("inserted id %q != returned id %q", inserted, id)
	}
	if pinned != id {
		t.Fatalf("pinned org %q != inserted id %q", pinned, id)
	}
}
