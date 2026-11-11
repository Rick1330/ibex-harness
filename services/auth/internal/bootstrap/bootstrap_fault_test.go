package bootstrap

import (
	"context"
	"database/sql"
	"database/sql/driver"
	"errors"
	"io"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/services/auth/internal/token"
	"github.com/google/uuid"
)

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
	if !ok {
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

// firstRunRows is the row set a clean first-run bootstrap reads: the new
// organization, the identity, and the memory-service outcome.
func firstRunRows() []faultRow {
	return []faultRow{
		organizationRow(true, nil),
		identityRow(),
		serviceTokenRow(outcomeInserted, uuid.NewString()),
	}
}

// organizationRow is the bootstrap_upsert_organization result.
func organizationRow(created bool, deletedAt driver.Value) faultRow {
	return faultRow{
		columns: []string{"created", "org_id", "deleted_at"},
		values:  []driver.Value{created, uuid.NewString(), deletedAt},
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

func TestBootstrapErrorPropagation(t *testing.T) {
	cfg := testConfig(t)

	closed, err := sql.Open("ibex-fault", "")
	if err != nil {
		t.Fatalf("open fault db: %v", err)
	}
	_ = closed.Close()
	if _, err := bootstrap(context.Background(), closed, cfg); err == nil {
		t.Fatal("bootstrap on a closed handle returned no error")
	}

	tests := []struct {
		name string
		f    faultConfig
		want string
	}{
		{
			name: "commit fails",
			f:    faultConfig{commit: errInjected, rows: firstRunRows()},
			want: "commit bootstrap transaction",
		},
		{
			name: "organization read fails",
			f:    faultConfig{query: errInjected},
			want: "insert organization",
		},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			db := openFaultDB(t, tc.f)
			_, err := bootstrap(context.Background(), db, cfg)
			if err == nil || !strings.Contains(err.Error(), tc.want) {
				t.Fatalf("bootstrap error = %v, want %q", err, tc.want)
			}
		})
	}
}

func TestBootstrapInTxPropagatesOrganizationFailure(t *testing.T) {
	db := openFaultDB(t, faultConfig{query: errInjected})
	tx := beginFaultTx(t, db)
	_, err := bootstrapInTx(context.Background(), tx, testConfig(t))
	if err == nil || !strings.Contains(err.Error(), "insert organization") {
		t.Fatalf("bootstrapInTx error = %v, want an insert-organization failure", err)
	}
	if !errors.Is(err, errInjected) {
		t.Fatalf("bootstrapInTx error = %v, want the injected fault in its chain", err)
	}
}

func TestCreateIdentityErrorPaths(t *testing.T) {
	cfg := testConfig(t)
	tests := []struct {
		name string
		f    faultConfig
		want string
	}{
		{
			name: "identity insert",
			f:    faultConfig{query: errInjected},
			want: "insert owner user and default agent",
		},
		{
			name: "identity scan",
			f:    faultConfig{scan: true},
			want: "insert owner user and default agent",
		},
		{
			name: "model policy insert",
			f:    faultConfig{exec: errInjected, rows: []faultRow{identityRow()}},
			want: "insert allow-all model policy",
		},
		{
			name: "bootstrap PAT insert",
			f:    faultConfig{exec: errInjected, execAfter: 1, rows: []faultRow{identityRow()}},
			want: "insert bootstrap PAT",
		},
		{
			name: "memory token write fails",
			f:    faultConfig{query: errInjected, queryAfter: 1, rows: []faultRow{identityRow()}},
			want: "write memory service token",
		},
		{
			name: "memory token prefix is taken",
			f: faultConfig{rows: []faultRow{
				identityRow(), serviceTokenRow(outcomePrefixConflict, ""),
			}},
			want: "already bound to another organization",
		},
		{
			name: "memory token is revoked",
			f: faultConfig{rows: []faultRow{
				identityRow(), serviceTokenRow(outcomeRevokedRefused, uuid.NewString()),
			}},
			want: "revoked",
		},
		{
			name: "memory token outcome is unknown",
			f: faultConfig{rows: []faultRow{
				identityRow(), serviceTokenRow("sideways", uuid.NewString()),
			}},
			want: "unrecognised outcome",
		},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			db := openFaultDB(t, tc.f)
			tx := beginFaultTx(t, db)
			_, err := createIdentity(context.Background(), tx, cfg, uuid.New())
			if err == nil || !strings.Contains(err.Error(), tc.want) {
				t.Fatalf("createIdentity error = %v, want %q", err, tc.want)
			}
		})
	}

	t.Run("success writes the memory token", func(t *testing.T) {
		db := openFaultDB(t, faultConfig{rows: []faultRow{
			identityRow(), serviceTokenRow(outcomeInserted, uuid.NewString()),
		}})
		tx := beginFaultTx(t, db)
		result, err := createIdentity(context.Background(), tx, cfg, uuid.New())
		if err != nil {
			t.Fatalf("createIdentity: %v", err)
		}
		if !result.MemoryTokenManaged || result.PAT == "" {
			t.Fatalf("result = %+v", result)
		}
	})
}

func TestReconcileServiceTokenErrorPaths(t *testing.T) {
	bearer := mustPAT(t)
	orgID := uuid.New()
	tests := []struct {
		name string
		f    faultConfig
		want string
	}{
		{
			name: "lock fails",
			f:    faultConfig{query: errInjected},
			want: "lock organization for memory token",
		},
		{
			name: "organization is gone",
			f:    faultConfig{rows: []faultRow{lockRow(false)}},
			want: "missing or soft-deleted",
		},
		{
			name: "no owner",
			f: faultConfig{rows: []faultRow{
				lockRow(true), subjectsRow(nil, uuid.NewString()),
			}},
			want: "no active owner",
		},
		{
			name: "no agent",
			f: faultConfig{rows: []faultRow{
				lockRow(true), subjectsRow(uuid.NewString(), nil),
			}},
			want: "no active agent",
		},
		{
			name: "subject lookup fails",
			f: faultConfig{
				query: errInjected, queryAfter: 1, rows: []faultRow{lockRow(true)},
			},
			want: "look up owner and agent",
		},
		{
			name: "token write fails",
			f: faultConfig{
				query: errInjected, queryAfter: 2,
				rows: []faultRow{lockRow(true), subjectsRow(uuid.NewString(), uuid.NewString())},
			},
			want: "write memory service token",
		},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			db := openFaultDB(t, tc.f)
			tx := beginFaultTx(t, db)
			err := reconcileServiceToken(context.Background(), tx, orgID, bearer)
			if err == nil || !strings.Contains(err.Error(), tc.want) {
				t.Fatalf("reconcileServiceToken error = %v, want %q", err, tc.want)
			}
		})
	}

	t.Run("success rebinds the managed row", func(t *testing.T) {
		db := openFaultDB(t, faultConfig{rows: []faultRow{
			lockRow(true),
			subjectsRow(uuid.NewString(), uuid.NewString()),
			serviceTokenRow(outcomeUpdated, uuid.NewString()),
		}})
		tx := beginFaultTx(t, db)
		if err := reconcileServiceToken(context.Background(), tx, orgID, bearer); err != nil {
			t.Fatalf("reconcileServiceToken: %v", err)
		}
	})
}

func TestOrganizationHelperErrors(t *testing.T) {
	cfg := testConfig(t)
	orgID := uuid.New()

	t.Run("read fails", func(t *testing.T) {
		db := openFaultDB(t, faultConfig{query: errInjected})
		tx := beginFaultTx(t, db)
		if _, err := insertOrganization(context.Background(), tx, orgInput{id: orgID, cfg: cfg}); err == nil {
			t.Fatal("insertOrganization returned no error")
		}
	})

	t.Run("fresh insert", func(t *testing.T) {
		db := openFaultDB(t, faultConfig{rows: []faultRow{organizationRow(true, nil)}})
		tx := beginFaultTx(t, db)
		result, err := insertOrganization(context.Background(), tx, orgInput{id: orgID, cfg: cfg})
		if err != nil {
			t.Fatalf("insertOrganization: %v", err)
		}
		if result.AlreadyBootstrapped {
			t.Fatal("insertOrganization reported an existing organization for a fresh insert")
		}
	})

	t.Run("existing organization", func(t *testing.T) {
		existing := uuid.New()
		row := faultRow{
			columns: []string{"created", "org_id", "deleted_at"},
			values:  []driver.Value{false, existing.String(), nil},
		}
		db := openFaultDB(t, faultConfig{rows: []faultRow{row}})
		tx := beginFaultTx(t, db)
		result, err := insertOrganization(context.Background(), tx, orgInput{id: orgID, cfg: cfg})
		if err != nil {
			t.Fatalf("insertOrganization: %v", err)
		}
		if !result.AlreadyBootstrapped || result.OrgID != existing {
			t.Fatalf("result = %+v, want already bootstrapped as %s", result, existing)
		}
	})

	t.Run("soft-deleted organization", func(t *testing.T) {
		row := faultRow{
			columns: []string{"created", "org_id", "deleted_at"},
			values:  []driver.Value{false, uuid.NewString(), time.Now().UTC()},
		}
		db := openFaultDB(t, faultConfig{rows: []faultRow{row}})
		tx := beginFaultTx(t, db)
		_, err := insertOrganization(context.Background(), tx, orgInput{id: orgID, cfg: cfg})
		if err == nil || !strings.Contains(err.Error(), "soft-deleted") {
			t.Fatalf("insertOrganization error = %v, want a soft-deleted refusal", err)
		}
	})
}

func TestIdentityHelperErrors(t *testing.T) {
	cfg := testConfig(t)
	orgID := uuid.New()
	cases := []struct {
		name string
		f    faultConfig
		call func(context.Context, *sql.Tx) error
	}{
		{"identity insert", faultConfig{query: errInjected}, func(ctx context.Context, tx *sql.Tx) error {
			_, _, err := insertIdentity(ctx, tx, identityInput{orgID: orgID, cfg: cfg})
			return err
		}},
		{"model policy insert", faultConfig{exec: errInjected}, func(ctx context.Context, tx *sql.Tx) error {
			return insertModelPolicy(ctx, tx, orgID)
		}},
		{"bootstrap PAT insert", faultConfig{exec: errInjected}, func(ctx context.Context, tx *sql.Tx) error {
			in := tokenInput{orgID: orgID, userID: uuid.New(), agentID: uuid.New(), name: cfg.PATName}
			_, err := insertToken(ctx, tx, in)
			return err
		}},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			db := openFaultDB(t, tc.f)
			tx := beginFaultTx(t, db)
			if err := tc.call(context.Background(), tx); err == nil {
				t.Fatalf("%s returned no error", tc.name)
			}
		})
	}
}

func TestServiceTokenHelperErrors(t *testing.T) {
	orgID := uuid.New()
	cases := []struct {
		name string
		f    faultConfig
		call func(context.Context, *sql.Tx) error
	}{
		{"query", faultConfig{query: errInjected}, func(ctx context.Context, tx *sql.Tx) error {
			return writeServiceToken(ctx, tx, serviceTokenInput{orgID: orgID, bearer: mustPAT(t)})
		}},
		{"scan", faultConfig{scan: true}, func(ctx context.Context, tx *sql.Tx) error {
			return writeServiceToken(ctx, tx, serviceTokenInput{orgID: orgID, bearer: mustPAT(t)})
		}},
		{"malformed token", faultConfig{}, func(ctx context.Context, tx *sql.Tx) error {
			return writeServiceToken(ctx, tx, serviceTokenInput{orgID: orgID, bearer: "not-a-pat"})
		}},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			db := openFaultDB(t, tc.f)
			tx := beginFaultTx(t, db)
			if err := tc.call(context.Background(), tx); err == nil {
				t.Fatalf("%s returned no error", tc.name)
			}
		})
	}

	t.Run("inserted and updated are success", func(t *testing.T) {
		for _, outcome := range []string{outcomeInserted, outcomeUpdated} {
			db := openFaultDB(t, faultConfig{rows: []faultRow{
				serviceTokenRow(outcome, uuid.NewString()),
			}})
			tx := beginFaultTx(t, db)
			in := serviceTokenInput{orgID: orgID, bearer: mustPAT(t)}
			if err := writeServiceToken(context.Background(), tx, in); err != nil {
				t.Fatalf("%s outcome: %v", outcome, err)
			}
		}
	})
}

func TestPrintBootstrapResultMemoryTokenVariants(t *testing.T) {
	t.Run("first run", func(t *testing.T) {
		var out strings.Builder
		if err := printBootstrapResult(&out, bootstrapResult{
			OrgID:              uuid.New(),
			PATPath:            "/run/ibex/bootstrap.pat",
			MemoryTokenManaged: true,
		}); err != nil {
			t.Fatalf("printBootstrapResult: %v", err)
		}
		if !strings.Contains(out.String(), "Memory token:") {
			t.Fatalf("summary missing the memory token line: %s", out.String())
		}
	})

	t.Run("already bootstrapped", func(t *testing.T) {
		var out strings.Builder
		if err := printBootstrapResult(&out, bootstrapResult{
			AlreadyBootstrapped: true,
			OrgID:               uuid.New(),
			MemoryTokenManaged:  true,
		}); err != nil {
			t.Fatalf("printBootstrapResult: %v", err)
		}
		if !strings.Contains(out.String(), "memory service token:") {
			t.Fatalf("summary missing the reconciliation line: %s", out.String())
		}
	})
}
