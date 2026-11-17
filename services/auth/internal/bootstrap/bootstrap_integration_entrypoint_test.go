//go:build integration

package bootstrap

import (
	"bytes"
	"context"
	"database/sql"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/crypto"
	"github.com/Rick1330/ibex-harness/services/auth/internal/token"
	"github.com/google/uuid"
)

// TestBootstrapIntegrationRunEntrypoint drives the shipped command entrypoint,
// not the inner helper: exit code, summary, and PAT file are the contract the
// one-shot container depends on.
type entrypointRun struct {
	code   int
	stdout string
	stderr string
}

type entrypointFixture struct {
	env     map[string]string
	patFile string
	db      *sql.DB
	slug    string
}

// newEntrypointFixture provisions a database and the environment the shipped
// command expects, with a PAT path inside the test's own directory.
func newEntrypointFixture(t *testing.T, orgName string) entrypointFixture {
	t.Helper()
	if os.Getenv("POSTGRES_TEST_DSN") == "" {
		t.Skip("POSTGRES_TEST_DSN not set")
	}
	db, dsn := openIntegrationDB(t)

	slug := uuid.NewString()
	t.Cleanup(func() { cleanupBootstrapOrg(t, db, slug) })

	patFile := filepath.Join(t.TempDir(), "bootstrap.pat")
	env := map[string]string{
		"POSTGRES_DSN":              dsn,
		"IBEX_BOOTSTRAP_PAT_FILE":   patFile,
		"IBEX_BOOTSTRAP_ORG_NAME":   orgName,
		"IBEX_BOOTSTRAP_ORG_SLUG":   slug,
		"IBEX_BOOTSTRAP_USER_EMAIL": "run-owner@example.com",
		"IBEX_BOOTSTRAP_USER_NAME":  "Owner",
		"IBEX_BOOTSTRAP_AGENT_NAME": "Default Agent",
		"IBEX_BOOTSTRAP_AGENT_SLUG": "default",
		"IBEX_BOOTSTRAP_PAT_NAME":   "Bootstrap PAT",
		// The shared compose test database already holds other suites'
		// organizations, so the entrypoint fixture is a deliberate second tenant;
		// IBEX_BOOTSTRAP_ALLOW_SECOND_ORG is what makes that explicit.
		"IBEX_BOOTSTRAP_ALLOW_SECOND_ORG": "true",
	}
	return entrypointFixture{env: env, patFile: patFile, db: db, slug: slug}
}

func runEntrypoint(t *testing.T, env map[string]string) entrypointRun {
	t.Helper()
	var stdout, stderr bytes.Buffer
	code := Run(&stdout, &stderr, mapGetenv(env))
	return entrypointRun{code: code, stdout: stdout.String(), stderr: stderr.String()}
}

func requireRunSucceeded(t *testing.T, run entrypointRun) {
	t.Helper()
	if run.code != 0 {
		t.Fatalf("Run exit = %d, stderr = %s", run.code, run.stderr)
	}
}

func assertSummaryNamesPATFile(t *testing.T, stdout, patFile string) {
	t.Helper()
	if strings.Contains(stdout, "ibex_pat_") {
		t.Fatalf("summary printed the PAT: %s", stdout)
	}
	if !strings.Contains(stdout, "IBEX_BOOTSTRAP_PAT_FILE="+patFile) {
		t.Fatalf("summary did not name the PAT file: %s", stdout)
	}
}

func readPATFile(t *testing.T, patFile string) []byte {
	t.Helper()
	t.Chdir(filepath.Dir(patFile))
	data, err := os.ReadFile("bootstrap.pat")
	if err != nil {
		t.Fatalf("read PAT file: %v", err)
	}
	return data
}

func assertPATFileValid(t *testing.T, patFile string) []byte {
	t.Helper()
	data := readPATFile(t, patFile)
	if _, err := token.ParsePAT(strings.TrimSpace(string(data))); err != nil {
		t.Fatalf("PAT file does not contain a PAT: %v", err)
	}
	info, err := os.Stat("bootstrap.pat")
	if err != nil {
		t.Fatalf("stat PAT file: %v", err)
	}
	if info.Mode().Perm() != 0o600 {
		t.Fatalf("PAT file mode = %o, want 600", info.Mode().Perm())
	}
	return data
}

// assertPATMatchesStoredHash verifies the delivered bearer against the committed
// admin-token hash, not just its shape.
func assertPATMatchesStoredHash(t *testing.T, db *sql.DB, slug, bearer string) {
	t.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), verifyTimeout)
	defer cancel()
	var hash string
	if err := db.QueryRowContext(ctx, `
		SELECT t.hash FROM ibex_core.tokens t
		INNER JOIN ibex_core.organizations o ON o.id = t.org_id
		WHERE o.slug = $1 AND t.type = 'pat' AND t.is_revoked = false`,
		slug,
	).Scan(&hash); err != nil {
		t.Fatalf("read stored PAT hash: %v", err)
	}
	ok, err := crypto.VerifyToken(bearer, hash, crypto.ProductionParams())
	if err != nil {
		t.Fatalf("verify delivered PAT: %v", err)
	}
	if !ok {
		t.Fatal("delivered PAT does not match the stored hash")
	}
}

// TestBootstrapIntegrationRunEntrypoint drives the shipped command entrypoint,
// not the inner helper: exit code, summary, and PAT file are the contract the
// one-shot container depends on.
func TestBootstrapIntegrationRunEntrypoint(t *testing.T) {
	f := newEntrypointFixture(t, "Bootstrap Entrypoint")

	run := runEntrypoint(t, f.env)
	requireRunSucceeded(t, run)
	assertSummaryNamesPATFile(t, run.stdout, f.patFile)
	data := assertPATFileValid(t, f.patFile)
	assertPATMatchesStoredHash(t, f.db, f.slug, strings.TrimSpace(string(data)))
}

// TestBootstrapIntegrationRunEntrypointRerun proves a second run reconciles
// without issuing or touching a PAT.
func TestBootstrapIntegrationRunEntrypointRerun(t *testing.T) {
	f := newEntrypointFixture(t, "Bootstrap Entrypoint Rerun")

	requireRunSucceeded(t, runEntrypoint(t, f.env))
	before := readPATFile(t, f.patFile)

	rerun := runEntrypoint(t, f.env)
	requireRunSucceeded(t, rerun)
	if strings.Contains(rerun.stdout, "IBEX_BOOTSTRAP_PAT_FILE=") {
		t.Fatalf("rerun touched the PAT: %s", rerun.stdout)
	}
	if !strings.Contains(rerun.stdout, "already bootstrapped") {
		t.Fatalf("rerun summary = %s", rerun.stdout)
	}
	after := readPATFile(t, f.patFile)
	if !bytes.Equal(before, after) {
		t.Fatal("rerun changed the delivered PAT file")
	}
}

// failingWriter reports an error after the summary exceeds the buffer, so Run's
// summary-error branch is exercised.
type failingWriter struct{}

func (failingWriter) Write([]byte) (int, error) {
	return 0, errors.New("summary stream closed")
}

// TestBootstrapIntegrationRunFailsWhenPATCannotBeWritten proves a PAT that
// cannot be delivered fails the one-shot and rolls the identity back, so a
// rerun issues a fresh PAT instead of leaving an organization with no
// recoverable credential.
func TestBootstrapIntegrationRunFailsWhenPATCannotBeWritten(t *testing.T) {
	if os.Getenv("POSTGRES_TEST_DSN") == "" {
		t.Skip("POSTGRES_TEST_DSN not set")
	}
	db, dsn := openIntegrationDB(t)

	slug := uuid.NewString()
	t.Cleanup(func() { cleanupBootstrapOrg(t, db, slug) })

	// A directory at the destination path passes the parent-directory check and
	// fails at rename time, before the transaction commits.
	patPath := filepath.Join(t.TempDir(), "bootstrap.pat")
	if err := os.Mkdir(patPath, 0o700); err != nil {
		t.Fatalf("seed destination directory: %v", err)
	}
	env := map[string]string{
		"POSTGRES_DSN":              dsn,
		"IBEX_BOOTSTRAP_PAT_FILE":   patPath,
		"IBEX_BOOTSTRAP_ORG_NAME":   "Bootstrap PAT Failure",
		"IBEX_BOOTSTRAP_ORG_SLUG":   slug,
		"IBEX_BOOTSTRAP_USER_EMAIL": "fail-owner@example.com",
		"IBEX_BOOTSTRAP_USER_NAME":  "Owner",
		"IBEX_BOOTSTRAP_AGENT_NAME": "Default Agent",
		"IBEX_BOOTSTRAP_AGENT_SLUG": "default",
		"IBEX_BOOTSTRAP_PAT_NAME":   "Bootstrap PAT",
		// The shared test database is not empty, so this fixture is a deliberate
		// second tenant and must say so before it reaches its own failure path.
		"IBEX_BOOTSTRAP_ALLOW_SECOND_ORG": "true",
	}

	var stdout, stderr bytes.Buffer
	if code := Run(&stdout, &stderr, mapGetenv(env)); code != 1 {
		t.Fatalf("Run exit = %d, want 1; stderr = %s", code, stderr.String())
	}
	if !strings.Contains(stderr.String(), "could not write the admin PAT") {
		t.Fatalf("stderr = %q, want a PAT delivery error", stderr.String())
	}

	ctx, tx := openServiceTx(t, db)
	var count int
	if err := tx.QueryRowContext(ctx,
		`SELECT count(*) FROM ibex_core.organizations WHERE slug = $1`, slug,
	).Scan(&count); err != nil {
		t.Fatalf("count organizations: %v", err)
	}
	if count != 0 {
		t.Fatalf("organizations with slug %q = %d, want 0 after a delivery failure", slug, count)
	}
}

// TestBootstrapIntegrationRunFailsWhenSummaryCannotBeWritten covers the last
// Run branch: the identity is committed, but the summary stream fails.
func TestBootstrapIntegrationRunFailsWhenSummaryCannotBeWritten(t *testing.T) {
	if os.Getenv("POSTGRES_TEST_DSN") == "" {
		t.Skip("POSTGRES_TEST_DSN not set")
	}
	db, dsn := openIntegrationDB(t)

	slug := uuid.NewString()
	t.Cleanup(func() { cleanupBootstrapOrg(t, db, slug) })

	env := map[string]string{
		"POSTGRES_DSN":                    dsn,
		"IBEX_BOOTSTRAP_PAT_FILE":         filepath.Join(t.TempDir(), "bootstrap.pat"),
		"IBEX_BOOTSTRAP_ORG_NAME":         "Bootstrap Summary Failure",
		"IBEX_BOOTSTRAP_ORG_SLUG":         slug,
		"IBEX_BOOTSTRAP_USER_EMAIL":       "out-owner@example.com",
		"IBEX_BOOTSTRAP_USER_NAME":        "Owner",
		"IBEX_BOOTSTRAP_AGENT_NAME":       "Default Agent",
		"IBEX_BOOTSTRAP_AGENT_SLUG":       "default",
		"IBEX_BOOTSTRAP_PAT_NAME":         "Bootstrap PAT",
		"IBEX_BOOTSTRAP_ALLOW_SECOND_ORG": "true",
	}

	var stderr bytes.Buffer
	if code := Run(failingWriter{}, &stderr, mapGetenv(env)); code != 1 {
		t.Fatalf("Run exit = %d, want 1; stderr = %s", code, stderr.String())
	}
	if !strings.Contains(stderr.String(), "write summary") {
		t.Fatalf("stderr = %q, want a summary-write error", stderr.String())
	}
}

// TestBootstrapIntegrationRunReportsRevokedToken covers Run's bootstrap-error
// branch: the database is reachable, but the identity write is refused.
func TestBootstrapIntegrationRunReportsRevokedToken(t *testing.T) {
	f := newBootstrapFixture(t)
	first := f.run()
	f.revoke(first)

	env := map[string]string{
		"POSTGRES_DSN":              f.cfg.PostgresDSN,
		"IBEX_BOOTSTRAP_PAT_FILE":   filepath.Join(t.TempDir(), "bootstrap.pat"),
		"IBEX_BOOTSTRAP_ORG_NAME":   f.cfg.OrgName,
		"IBEX_BOOTSTRAP_ORG_SLUG":   f.cfg.OrgSlug,
		"IBEX_BOOTSTRAP_USER_EMAIL": f.cfg.UserEmail,
		"IBEX_BOOTSTRAP_USER_NAME":  f.cfg.UserName,
		"IBEX_BOOTSTRAP_AGENT_NAME": f.cfg.AgentName,
		"IBEX_BOOTSTRAP_AGENT_SLUG": f.cfg.AgentSlug,
		"IBEX_BOOTSTRAP_PAT_NAME":   f.cfg.PATName,
		"IBEX_MEMORY_API_TOKEN":     f.cfg.MemoryToken,
	}

	var stdout, stderr bytes.Buffer
	if code := Run(&stdout, &stderr, mapGetenv(env)); code != 1 {
		t.Fatalf("Run exit = %d, want 1; stderr = %s", code, stderr.String())
	}
	if !strings.Contains(stderr.String(), "revoked") {
		t.Fatalf("stderr = %q, want a revoked-token refusal", stderr.String())
	}
	if stdout.Len() != 0 {
		t.Fatalf("stdout = %q, want no summary", stdout.String())
	}
}
