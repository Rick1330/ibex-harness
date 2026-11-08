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

	"github.com/Rick1330/ibex-harness/services/auth/internal/token"
	"github.com/google/uuid"
)

// The fault driver injects failures at each database boundary. It exists so the
// defensive error returns in bootstrap.go are exercised deterministically: a
// real server cannot be made to fail a single Exec or Commit on demand, and
// mocking the code under test would not prove anything.
var errInjected = errors.New("injected database fault")

type faultConfig struct {
	begin  error
	exec   error
	query  error
	ping   error
	commit error
	result error
	// execAfter and queryAfter are the number of successful calls before the
	// configured error fires, so a test can reach the second or third statement
	// of an orchestrator.
	execAfter  int
	queryAfter int
	// rowValue is returned by the first rowQueries queries, which lets a test
	// satisfy a SELECT and then make a later one return no rows.
	rowValue   string
	rowQueries int
	scan       bool
	// rowsAffected is reported by a successful Exec.
	rowsAffected int64
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
	return &faultRows{}, nil
}

type faultResult struct{}

func (faultResult) LastInsertId() (int64, error) { return 0, fault.result }
func (faultResult) RowsAffected() (int64, error) { return fault.rowsAffected, fault.result }

type faultRows struct {
	sent bool
}

func (*faultRows) Columns() []string { return []string{"id"} }
func (*faultRows) Close() error      { return nil }

func (r *faultRows) Next(dest []driver.Value) error {
	if r.sent {
		return io.EOF
	}
	switch {
	case fault.scan:
		r.sent = true
		dest[0] = "not-a-uuid"
		return nil
	case fault.rowValue != "" && queryCalls <= fault.rowQueries:
		r.sent = true
		dest[0] = fault.rowValue
		return nil
	default:
		return io.EOF
	}
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
			name: "session setup fails",
			f:    faultConfig{exec: errInjected},
			want: "set service-account session",
		},
		{
			name: "commit fails",
			f:    faultConfig{commit: errInjected, rowsAffected: 1},
			want: "commit bootstrap transaction",
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
	db := openFaultDB(t, faultConfig{exec: errInjected})
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
		{"owner insert", faultConfig{exec: errInjected}, "insert owner user"},
		{"agent insert", faultConfig{exec: errInjected, execAfter: 1}, "insert agent"},
		{"policy insert", faultConfig{exec: errInjected, execAfter: 2}, "insert allow-all model policy"},
		{"policy epoch insert", faultConfig{exec: errInjected, execAfter: 3}, "insert model policy epoch"},
		{"bootstrap PAT insert", faultConfig{exec: errInjected, execAfter: 4}, "insert bootstrap PAT"},
		{"memory token insert", faultConfig{exec: errInjected, execAfter: 6}, "insert memory service token"},
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
		db := openFaultDB(t, faultConfig{})
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
	agentID := uuid.NewString()
	tests := []struct {
		name string
		f    faultConfig
		want string
	}{
		{"lock fails", faultConfig{query: errInjected}, "lock organization"},
		{"no owner", faultConfig{rowValue: agentID, rowQueries: 1}, "no active owner"},
		{"owner lookup fails", faultConfig{query: errInjected, queryAfter: 1, rowValue: agentID, rowQueries: 1}, "look up owner"},
		{"no agent", faultConfig{rowValue: agentID, rowQueries: 2}, "no active agent"},
		{"agent lookup fails", faultConfig{query: errInjected, queryAfter: 2, rowValue: agentID, rowQueries: 2}, "look up agent"},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			db := openFaultDB(t, tc.f)
			tx := beginFaultTx(t, db)
			err := reconcileServiceToken(context.Background(), tx, uuid.New(), bearer)
			if err == nil || !strings.Contains(err.Error(), tc.want) {
				t.Fatalf("reconcileServiceToken error = %v, want %q", err, tc.want)
			}
		})
	}
}

func TestOrganizationHelperErrors(t *testing.T) {
	cfg := testConfig(t)
	orgID := uuid.New()

	t.Run("rows affected", func(t *testing.T) {
		db := openFaultDB(t, faultConfig{result: errInjected})
		tx := beginFaultTx(t, db)
		if _, err := insertOrganization(context.Background(), tx, orgInput{id: orgID, cfg: cfg}); err == nil {
			t.Fatal("insertOrganization returned no error")
		}
	})

	t.Run("existing lookup", func(t *testing.T) {
		db := openFaultDB(t, faultConfig{query: errInjected})
		tx := beginFaultTx(t, db)
		if _, err := insertOrganization(context.Background(), tx, orgInput{id: orgID, cfg: cfg}); err == nil {
			t.Fatal("insertOrganization returned no error")
		}
	})

	t.Run("fresh insert", func(t *testing.T) {
		db := openFaultDB(t, faultConfig{rowsAffected: 1})
		tx := beginFaultTx(t, db)
		result, err := insertOrganization(context.Background(), tx, orgInput{id: orgID, cfg: cfg})
		if err != nil {
			t.Fatalf("insertOrganization: %v", err)
		}
		if result.AlreadyBootstrapped {
			t.Fatal("insertOrganization reported an existing organization for a fresh insert")
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
		{"owner insert", faultConfig{exec: errInjected}, func(ctx context.Context, tx *sql.Tx) error {
			_, _, err := insertIdentity(ctx, tx, identityInput{orgID: orgID, cfg: cfg})
			return err
		}},
		{"agent insert", faultConfig{exec: errInjected, execAfter: 1}, func(ctx context.Context, tx *sql.Tx) error {
			_, _, err := insertIdentity(ctx, tx, identityInput{orgID: orgID, cfg: cfg})
			return err
		}},
		{"model policy insert", faultConfig{exec: errInjected}, func(ctx context.Context, tx *sql.Tx) error {
			return insertModelPolicy(ctx, tx, orgID)
		}},
		{"model policy epoch", faultConfig{exec: errInjected, execAfter: 1}, func(ctx context.Context, tx *sql.Tx) error {
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
	row := serviceTokenRow{id: uuid.New(), orgID: orgID}
	cases := []struct {
		name string
		f    faultConfig
		call func(context.Context, *sql.Tx) error
	}{
		{"lookup", faultConfig{query: errInjected, queryAfter: 1}, func(ctx context.Context, tx *sql.Tx) error {
			in := serviceTokenInput{orgID: orgID, bearer: mustPAT(t)}
			return writeServiceToken(ctx, tx, in)
		}},
		{"prefix check", faultConfig{query: errInjected}, func(ctx context.Context, tx *sql.Tx) error {
			in := serviceTokenInput{orgID: orgID, bearer: mustPAT(t)}
			err := writeServiceToken(ctx, tx, in)
			if err == nil || !strings.Contains(err.Error(), "check memory token prefix") {
				t.Fatalf("writeServiceToken error = %v, want a prefix-check failure", err)
			}
			return err
		}},
		{"scan", faultConfig{scan: true}, func(ctx context.Context, tx *sql.Tx) error {
			_, err := findServiceTokens(ctx, tx, orgID)
			return err
		}},
		{"update", faultConfig{exec: errInjected}, func(ctx context.Context, tx *sql.Tx) error {
			return updateServiceToken(ctx, tx, row)
		}},
		{"insert", faultConfig{exec: errInjected}, func(ctx context.Context, tx *sql.Tx) error {
			in := serviceTokenInput{orgID: orgID, bearer: mustPAT(t)}
			return insertServiceToken(ctx, tx, in, serviceTokenRow{})
		}},
		{"revoke duplicates", faultConfig{exec: errInjected}, func(ctx context.Context, tx *sql.Tx) error {
			return revokeDuplicateServiceTokens(ctx, tx, orgID, []serviceTokenRow{row})
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

	t.Run("revoked duplicate is skipped", func(t *testing.T) {
		db := openFaultDB(t, faultConfig{})
		tx := beginFaultTx(t, db)
		rows := []serviceTokenRow{{id: uuid.New(), revoked: true}}
		if err := revokeDuplicateServiceTokens(context.Background(), tx, orgID, rows); err != nil {
			t.Fatalf("revokeDuplicateServiceTokens: %v", err)
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
