//go:build integration

package repository_test

import (
	"context"
	"database/sql"
	"database/sql/driver"
	"errors"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/infra/testing/testutil"
	"github.com/Rick1330/ibex-harness/services/auth/internal/repository"
	"github.com/google/uuid"
	"github.com/lib/pq"
)

// statementLog records every statement the wrapped driver is asked to run.
// It is shared by every connection in the pool, which is what the test wants:
// one operation, one ordered list of statements.
type statementLog struct {
	mu    sync.Mutex
	stmts []string
}

func (l *statementLog) add(query string) {
	l.mu.Lock()
	defer l.mu.Unlock()
	l.stmts = append(l.stmts, query)
}

func (l *statementLog) snapshot() []string {
	l.mu.Lock()
	defer l.mu.Unlock()
	return append([]string(nil), l.stmts...)
}

func (l *statementLog) reset() {
	l.mu.Lock()
	defer l.mu.Unlock()
	l.stmts = nil
}

var (
	captureOnce sync.Once
	captureLog  = &statementLog{}
)

const captureDriverName = "ibex-auth-capture"

// captureDriver wraps the real lib/pq driver and records each statement before
// delegating. It exists so the test proves what the repository sends to the
// server, not what a mock was told to expect.
type captureDriver struct {
	inner driver.Driver
	log   *statementLog
}

// Open wraps the lib/pq connection so every statement it carries is recorded.
func (d captureDriver) Open(name string) (driver.Conn, error) {
	conn, err := d.inner.Open(name)
	if err != nil {
		return nil, err
	}
	return &captureConn{Conn: conn, log: d.log}, nil
}

// captureConn records the statements database/sql can send through a connection.
// BeginTx is forwarded so Begin/Commit stay invisible, matching the server.
type captureConn struct {
	driver.Conn
	log *statementLog
}

func (c *captureConn) Prepare(query string) (driver.Stmt, error) {
	c.log.add(query)
	return c.Conn.Prepare(query)
}

// ExecContext records the statement and forwards it when the underlying
// connection supports context-aware execution.
func (c *captureConn) ExecContext(ctx context.Context, query string, args []driver.NamedValue) (driver.Result, error) {
	execer, ok := c.Conn.(driver.ExecerContext)
	if !ok {
		return nil, driver.ErrSkip
	}
	c.log.add(query)
	return execer.ExecContext(ctx, query, args)
}

// QueryContext records the statement and forwards it when the underlying
// connection supports context-aware queries.
func (c *captureConn) QueryContext(ctx context.Context, query string, args []driver.NamedValue) (driver.Rows, error) {
	queryer, ok := c.Conn.(driver.QueryerContext)
	if !ok {
		return nil, driver.ErrSkip
	}
	c.log.add(query)
	return queryer.QueryContext(ctx, query, args)
}

// BeginTx forwards to the context-aware beginner when available. It records
// nothing: a transaction boundary is not a statement sent to the server.
func (c *captureConn) BeginTx(ctx context.Context, opts driver.TxOptions) (driver.Tx, error) {
	if beginner, ok := c.Conn.(driver.ConnBeginTx); ok {
		return beginner.BeginTx(ctx, opts)
	}
	return c.Conn.Begin()
}

// CheckNamedValue forwards to lib/pq so driver.Valuer handling (google/uuid)
// behaves exactly as it does without the wrapper.
func (c *captureConn) CheckNamedValue(nv *driver.NamedValue) error {
	if checker, ok := c.Conn.(driver.NamedValueChecker); ok {
		return checker.CheckNamedValue(nv)
	}
	return driver.ErrSkip
}

// openCaptureDB registers the recording driver once per process and opens a
// pool that routes every statement through it.
func openCaptureDB(t *testing.T, dsn string) *sql.DB {
	t.Helper()
	captureOnce.Do(func() {
		sql.Register(captureDriverName, captureDriver{inner: &pq.Driver{}, log: captureLog})
	})
	db, err := sql.Open(captureDriverName, dsn)
	if err != nil {
		t.Fatalf("open capture db: %v", err)
	}
	t.Cleanup(func() { _ = db.Close() })
	return db
}

// tenantCaptureEnv holds the seeded ids used by the per-operation cases.
type tenantCaptureEnv struct {
	orgID, userID, agentID string
	activePrefix           string
	pendingCiphertext      []byte
}

// seedTenantCaptureEnv creates one organisation with a user, an agent and a
// token, and returns the ids every capture case addresses.
func seedTenantCaptureEnv(t *testing.T, seedRepo *repository.TokensRepository, db *sql.DB) tenantCaptureEnv {
	t.Helper()
	label := uuid.NewString()[:8]
	orgID := testutil.SeedOrganization(t, db, "Capture Org "+label, "capture-"+label)
	userID := testutil.SeedUser(t, db, orgID, "capture-"+label+"@test.local", "Capture User")
	agentID := testutil.SeedAgent(t, db, orgID, userID, "Capture Agent", "capture-agent-"+label)
	prefix := "ibex_pat_" + uuid.NewString()
	if _, err := seedRepo.InsertTestToken(context.Background(), repository.TestTokenParams{
		OrgID: orgID, Prefix: prefix, Hash: "hash-" + label, Name: "capture", Permissions: 1,
	}); err != nil {
		t.Fatalf("seed token: %v", err)
	}
	return tenantCaptureEnv{orgID: orgID, userID: userID, agentID: agentID, activePrefix: prefix}
}

// tenantCaptureCase is one repository call and the statement fragment that
// proves it reached the intended table.
type tenantCaptureCase struct {
	name string
	want string
	run  func(context.Context, *captureRepos) error
}

type captureRepos struct {
	tokens  *repository.TokensRepository
	users   *repository.UsersRepository
	agents  *repository.AgentsRepository
	totp    *repository.TotpSecretRepo
	creds   *repository.ProviderCredentialsRepository
	env     tenantCaptureEnv
	tokenID string
}

// newCaptureRepos binds each repository to the recording pool so the same
// operations can be inspected statement by statement.
func newCaptureRepos(t *testing.T, db *sql.DB, env tenantCaptureEnv) *captureRepos {
	t.Helper()
	tokens := repository.RequireTokensRepository(t, db, nil)
	creds, err := repository.NewProviderCredentialsRepository(db, nil)
	if err != nil {
		t.Fatalf("NewProviderCredentialsRepository: %v", err)
	}
	return &captureRepos{
		tokens: tokens,
		users:  repository.NewUsersRepository(db, nil),
		agents: repository.NewAgentsRepository(db, nil),
		totp:   repository.NewTotpSecretRepo(db),
		creds:  creds,
		env:    env,
	}
}

// seedCaptureRows creates the rows the read/update cases operate on. It runs
// through the same repositories (and thus the same pin) but outside the
// assertion window.
func seedCaptureRows(t *testing.T, r *captureRepos) {
	t.Helper()
	ctx := context.Background()
	id, err := r.tokens.CreateToken(ctx, repository.CreateTokenParams{
		ID: uuid.NewString(), OrgID: r.env.orgID, Name: "capture-create",
		Hash: "hash-" + uuid.NewString(), Prefix: "ibex_pat_" + uuid.NewString(), Permissions: 3,
	})
	if err != nil {
		t.Fatalf("seed CreateToken: %v", err)
	}
	r.tokenID = id
	r.env.pendingCiphertext = []byte("totp-cipher")
	if err := r.totp.UpsertPending(ctx, repository.TotpSecretRow{
		OrgID: r.env.orgID, UserID: r.env.userID,
		Ciphertext: r.env.pendingCiphertext, WrappedDEK: []byte("dek"), EncryptionKeyID: "v1",
	}); err != nil {
		t.Fatalf("seed UpsertPending: %v", err)
	}
	if _, err := r.creds.Upsert(ctx, repository.ProviderCredentialRow{
		OrgID: r.env.orgID, ProviderName: "openai",
		Ciphertext: []byte("ct"), WrappedDEK: []byte("dek"), EncryptionKeyID: "v1",
		KeyHint: "hint", Status: "active",
	}); err != nil {
		t.Fatalf("seed provider credential: %v", err)
	}
}

// tenantCaptureCases returns one repository operation per tenant path, paired
// with a fragment that identifies the table it must reach.
func tenantCaptureCases() []tenantCaptureCase {
	return []tenantCaptureCase{
		{"CreateToken", "INSERT INTO ibex_core.tokens", func(ctx context.Context, r *captureRepos) error {
			_, err := r.tokens.CreateToken(ctx, repository.CreateTokenParams{
				ID: uuid.NewString(), OrgID: r.env.orgID, Name: "capture-2",
				Hash: "hash-" + uuid.NewString(), Prefix: "ibex_pat_" + uuid.NewString(), Permissions: 1,
			})
			return err
		}},
		{"RevokeToken", "UPDATE ibex_core.tokens", func(ctx context.Context, r *captureRepos) error {
			return r.tokens.RevokeToken(ctx, repository.RevokeTokenInput{OrgID: r.env.orgID, TokenID: r.tokenID})
		}},
		{"ListActiveTokenIDsByUser", "AND user_id = $2::uuid", func(ctx context.Context, r *captureRepos) error {
			_, err := r.tokens.ListActiveTokenIDsByUser(ctx, repository.OrgUserRef{OrgID: r.env.orgID, UserID: r.env.userID})
			return err
		}},
		{"ListTokens", "ORDER BY created_at DESC, id DESC LIMIT", func(ctx context.Context, r *captureRepos) error {
			_, _, err := r.tokens.ListTokens(ctx, r.env.orgID, "", 10)
			return err
		}},
		{"Users.GetByIDAndOrg", "FROM ibex_core.users", func(ctx context.Context, r *captureRepos) error {
			rec, err := r.users.GetByIDAndOrg(ctx, uuid.MustParse(r.env.userID), uuid.MustParse(r.env.orgID))
			if err == nil && rec == nil {
				return errors.New("seeded user not found")
			}
			return err
		}},
		{"Agents.GetByIDAndOrg", "FROM ibex_core.agents", func(ctx context.Context, r *captureRepos) error {
			rec, err := r.agents.GetByIDAndOrg(ctx, uuid.MustParse(r.env.agentID), uuid.MustParse(r.env.orgID))
			if err == nil && rec == nil {
				return errors.New("seeded agent not found")
			}
			return err
		}},
		{"Totp.UpsertPending", "INSERT INTO ibex_core.user_totp_secrets", func(ctx context.Context, r *captureRepos) error {
			return r.totp.UpsertPending(ctx, repository.TotpSecretRow{
				OrgID: r.env.orgID, UserID: r.env.userID,
				Ciphertext: []byte("totp-cipher-2"), WrappedDEK: []byte("dek"), EncryptionKeyID: "v1",
			})
		}},
		{"Totp.Get", "FROM ibex_core.user_totp_secrets", func(ctx context.Context, r *captureRepos) error {
			_, err := r.totp.Get(ctx, r.env.orgID, r.env.userID)
			return err
		}},
		{"Totp.ConfirmCiphertext", "UPDATE ibex_core.user_totp_secrets", func(ctx context.Context, r *captureRepos) error {
			return r.totp.ConfirmCiphertext(ctx, repository.ConfirmCiphertextParams{
				OrgID: r.env.orgID, UserID: r.env.userID,
				Ciphertext: []byte("totp-cipher-2"), At: time.Now().UTC(),
			})
		}},
		{"ProviderCredentials.Upsert", "INSERT INTO ibex_core.provider_credentials", func(ctx context.Context, r *captureRepos) error {
			_, err := r.creds.Upsert(ctx, repository.ProviderCredentialRow{
				OrgID: r.env.orgID, ProviderName: "anthropic",
				Ciphertext: []byte("ct2"), WrappedDEK: []byte("dek"), EncryptionKeyID: "v1",
				KeyHint: "hint2", Status: "active",
			})
			return err
		}},
		{"ProviderCredentials.FindByOrgProvider", "FROM ibex_core.provider_credentials", func(ctx context.Context, r *captureRepos) error {
			_, err := r.creds.FindByOrgProvider(ctx, r.env.orgID, "openai")
			return err
		}},
		{"ProviderCredentials.ListByOrg", "ORDER BY provider_name ASC", func(ctx context.Context, r *captureRepos) error {
			_, err := r.creds.ListByOrg(ctx, r.env.orgID)
			return err
		}},
		{"ProviderCredentials.Delete", "DELETE FROM ibex_core.provider_credentials", func(ctx context.Context, r *captureRepos) error {
			return r.creds.Delete(ctx, r.env.orgID, "anthropic")
		}},
	}
}

// TestRepositoryTenantPinningStatements proves every tenant operation issues
// SET LOCAL ROLE ibex_app followed by a bound app.current_org_id, and that no
// repository writes the retired app.is_service_account flag.
func TestRepositoryTenantPinningStatements(t *testing.T) {
	dsn, cleanup := testutil.SetupPostgres(t)
	defer cleanup()

	seedDB := testutil.OpenDB(t, dsn)
	defer func() { _ = seedDB.Close() }()
	db := openCaptureDB(t, dsn)
	seedRepo := repository.RequireTokensRepository(t, seedDB, nil)
	env := seedTenantCaptureEnv(t, seedRepo, seedDB)
	repos := newCaptureRepos(t, db, env)
	seedCaptureRows(t, repos)

	for _, tc := range tenantCaptureCases() {
		t.Run(tc.name, func(t *testing.T) {
			captureLog.reset()
			if err := tc.run(context.Background(), repos); err != nil {
				t.Fatalf("%s: %v", tc.name, err)
			}
			stmts := captureLog.snapshot()
			assertStatementContains(t, stmts, "SET LOCAL ROLE ibex_app")
			assertStatementContains(t, stmts, "app.current_org_id")
			assertStatementContains(t, stmts, tc.want)
			assertNoServiceAccountGUC(t, stmts)
		})
	}
}

// TestRepositoryTokenLookupUsesDefiner proves the validation lookup is one
// statement against the SECURITY DEFINER reader, with no role pin and no tenant
// GUC — the properties that make it work under a future ibex_runtime DSN.
func TestRepositoryTokenLookupUsesDefiner(t *testing.T) {
	dsn, cleanup := testutil.SetupPostgres(t)
	defer cleanup()

	seedDB := testutil.OpenDB(t, dsn)
	defer func() { _ = seedDB.Close() }()
	db := openCaptureDB(t, dsn)
	seedRepo := repository.RequireTokensRepository(t, seedDB, nil)
	env := seedTenantCaptureEnv(t, seedRepo, seedDB)
	repo := repository.RequireTokensRepository(t, db, nil)

	captureLog.reset()
	row, err := repo.FindActiveByPrefix(context.Background(), env.activePrefix)
	if err != nil {
		t.Fatalf("FindActiveByPrefix: %v", err)
	}
	if row.OrgID != env.orgID {
		t.Fatalf("org_id = %s, want %s", row.OrgID, env.orgID)
	}

	stmts := captureLog.snapshot()
	if len(stmts) != 1 {
		t.Fatalf("token lookup ran %d statements, want exactly 1: %v", len(stmts), stmts)
	}
	if got := strings.TrimSpace(stmts[0]); got != findActiveTokenSQLForTest {
		t.Fatalf("token lookup statement = %q, want %q", got, findActiveTokenSQLForTest)
	}
	if strings.Contains(stmts[0], "SET LOCAL ROLE") || strings.Contains(stmts[0], "app.current_org_id") {
		t.Fatalf("token lookup pinned a role or tenant selector: %v", stmts)
	}
	assertNoServiceAccountGUC(t, stmts)
}

// findActiveTokenSQLForTest is the exact statement the repository must send.
const findActiveTokenSQLForTest = `SELECT * FROM ibex_core.auth_find_token_by_prefix($1)`

// TestRepositoryTenantIDFailsClosed proves an empty or malformed org id is
// rejected in Go before any SQL runs.
func TestRepositoryTenantIDFailsClosed(t *testing.T) {
	dsn, cleanup := testutil.SetupPostgres(t)
	defer cleanup()

	db := openCaptureDB(t, dsn)
	repo := repository.RequireTokensRepository(t, db, nil)

	for _, orgID := range []string{"", "not-a-uuid", uuid.Nil.String()} {
		captureLog.reset()
		_, _, err := repo.ListTokens(context.Background(), orgID, "", 10)
		if !errors.Is(err, repository.ErrInvalidTenantID) {
			t.Fatalf("org %q: err = %v, want ErrInvalidTenantID", orgID, err)
		}
		if stmts := captureLog.snapshot(); len(stmts) != 0 {
			t.Fatalf("org %q: ran %d statements before validation: %v", orgID, len(stmts), stmts)
		}
	}
}

// assertStatementContains requires at least one recorded statement to contain
// fragment, which is how each case proves it reached its table.
func assertStatementContains(t *testing.T, stmts []string, fragment string) {
	t.Helper()
	for _, stmt := range stmts {
		if strings.Contains(stmt, fragment) {
			return
		}
	}
	t.Fatalf("no statement contained %q: %v", fragment, stmts)
}

// assertNoServiceAccountGUC fails if any recorded statement still sets the
// retired app.is_service_account flag.
func assertNoServiceAccountGUC(t *testing.T, stmts []string) {
	t.Helper()
	for _, stmt := range stmts {
		if strings.Contains(stmt, "app.is_service_account") {
			t.Fatalf("repository still sets the retired service-account GUC: %q", stmt)
		}
	}
}
