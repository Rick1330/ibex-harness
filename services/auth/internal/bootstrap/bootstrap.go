// Package bootstrap creates the first v1-single-node organization, owner user,
// default agent, allow-all model policy, and a bootstrap PAT in one transaction.
// The model policy is written by the organization definer, in the same statement
// that creates the organization, so it cannot be installed into a tenant that
// already exists. It is idempotent per organization slug, never rotates the PAT,
// and reconciles the scoped memory service token without reactivating a revoked
// row.
package bootstrap

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"time"

	"github.com/Rick1330/ibex-harness/packages/crypto"
	"github.com/Rick1330/ibex-harness/packages/permissions"
	"github.com/Rick1330/ibex-harness/services/auth/internal/token"
	"github.com/google/uuid"

	// Register the PostgreSQL driver for database/sql.
	_ "github.com/lib/pq"
)

const (
	defaultOrgName    = "IBEX Harness"
	defaultOrgSlug    = "ibex"
	defaultUserEmail  = "owner@ibex.local"
	defaultUserName   = "Owner"
	defaultAgentName  = "Default Agent"
	defaultAgentSlug  = "default"
	defaultPATName    = "Bootstrap PAT"
	bootstrapTimeout  = 30 * time.Second
	postgresPingLimit = 10 * time.Second

	bootstrapErrorFormat = "ibex-bootstrap: %v\n"
	bootstrapBanner      = "======================================================================\n"
	bootstrapRule        = "----------------------------------------------------------------------\n"
)

var (
	// slugPattern and emailPattern mirror the CHECK constraints in
	// 000002_organizations / 000007_create_agents and 000006_create_users.
	slugPattern  = regexp.MustCompile(`^[a-z0-9-]+$`)
	emailPattern = regexp.MustCompile(`^[^@]+@[^@]+\.[^@]+$`)
)

// bootstrapConfig is the complete input set. Every field except PostgresDSN
// has a default, so an operator only has to supply a DSN.
type bootstrapConfig struct {
	PostgresDSN string
	OrgName     string
	OrgSlug     string
	UserEmail   string
	UserName    string
	AgentName   string
	AgentSlug   string
	PATName     string
	// PATFile is where the one-time admin PAT is written. It is required: the
	// command never prints the credential, because a container or CI log would
	// retain it.
	PATFile string
	// MemoryToken is an optional PAT-shaped service token the memory service
	// accepts for internal context/worker calls. It is inserted as a
	// type=service_token row with MemoryRead|MemoryWrite.
	MemoryToken string
}

type bootstrapResult struct {
	AlreadyBootstrapped bool
	OrgID               uuid.UUID
	UserID              uuid.UUID
	AgentID             uuid.UUID
	PAT                 string
	PATPath             string
	MemoryTokenManaged  bool
}

// The input structs keep the SQL helpers below four arguments (including the
// context and transaction) so the Code Health complexity budget holds.

type orgInput struct {
	id  uuid.UUID
	cfg bootstrapConfig
}

type identityInput struct {
	orgID uuid.UUID
	cfg   bootstrapConfig
}

type tokenInput struct {
	orgID   uuid.UUID
	userID  uuid.UUID
	agentID uuid.UUID
	name    string
}

type serviceTokenInput struct {
	orgID  uuid.UUID
	bearer string
}

// subjectIDs are the organization's current owner and default agent. Either may
// be absent, which callers must not treat as a usable binding.
type subjectIDs struct {
	owner uuid.NullUUID
	agent uuid.NullUUID
}

// The definer statements. Migration 000069 moved every write behind a
// SECURITY DEFINER function owned by ibex_service, because 000063's tenant
// policy admits current_user = 'ibex_service' and ibex_service is NOBYPASSRLS:
// a bootstrap process that pins the least-privilege ibex_bootstrap login holds
// no table privilege at all. Each definer returns data, or a named outcome,
// rather than raising a business error, so the operator-facing text stays here.
const (
	// upsertOrganizationSQL creates the organization and, on the created branch,
	// its allow-all model policy and epoch. Both are written by this one definer:
	// the policy belongs to the moment of creation, so a caller that names an
	// existing slug receives created = false and no policy row.
	upsertOrganizationSQL = `
		SELECT created, org_id, deleted_at
		FROM ibex_core.bootstrap_upsert_organization($1, $2, $3)`
	// lockOrganizationSQL returns whether a non-deleted row was locked.
	lockOrganizationSQL = `SELECT ibex_core.bootstrap_lock_organization($1)`
	lookupSubjectsSQL   = `
		SELECT owner_id, agent_id
		FROM ibex_core.bootstrap_lookup_subjects($1)`
	createIdentitySQL = `
		SELECT user_id, agent_id
		FROM ibex_core.bootstrap_create_identity($1, $2, $3, $4, $5, $6, $7)`
	// insertPATSQL returns the token id Go already generated; it is not read.
	insertPATSQL          = `SELECT ibex_core.bootstrap_insert_pat($1, $2, $3, $4, $5, $6, $7, $8)`
	upsertServiceTokenSQL = `
		SELECT outcome, token_id
		FROM ibex_core.bootstrap_upsert_service_token($1, $2, $3, $4)`
)

// The named outcomes bootstrap_upsert_service_token reports.
const (
	// outcomeInserted means no managed row existed and one was created.
	outcomeInserted = "inserted"
	// outcomeUpdated means the managed row was re-bound to the new value.
	outcomeUpdated = "updated"
	// outcomePrefixConflict means another organization owns the prefix.
	outcomePrefixConflict = "prefix_conflict"
	// outcomeRevokedRefused means the managed row is revoked and must stay so.
	outcomeRevokedRefused = "revoked_refused"
)

// Run executes the bootstrap command and returns a process exit code.
func Run(stdout, stderr io.Writer, getenv func(string) string) int {
	cfg, err := loadBootstrapConfig(getenv)
	if err != nil {
		writef(stderr, bootstrapErrorFormat, err)
		return 1
	}

	db, err := sql.Open("postgres", cfg.PostgresDSN)
	if err != nil {
		writef(stderr, "ibex-bootstrap: open postgres: %v\n", err)
		return 1
	}
	defer func() { _ = db.Close() }()

	pingCtx, cancel := context.WithTimeout(context.Background(), postgresPingLimit)
	defer cancel()
	if err := db.PingContext(pingCtx); err != nil {
		writef(stderr, "ibex-bootstrap: connect postgres: %v\n", err)
		return 1
	}

	result, err := bootstrap(context.Background(), db, cfg)
	if err != nil {
		writef(stderr, bootstrapErrorFormat, err)
		return 1
	}
	if err := printBootstrapResult(stdout, result); err != nil {
		writef(stderr, "ibex-bootstrap: write summary: %v\n", err)
		return 1
	}
	return 0
}

// deliverBootstrapPAT writes the one-time PAT before the transaction commits.
// A delivery failure therefore rolls back the whole identity, so a rerun issues
// a fresh PAT instead of leaving an organization whose only credential was
// lost. A commit failure after the write leaves an unusable file that the next
// run overwrites.
func deliverBootstrapPAT(cfg bootstrapConfig, result bootstrapResult) (bootstrapResult, error) {
	if result.PAT == "" {
		return result, nil
	}
	if err := writeRestrictedFile(cfg.PATFile, result.PAT); err != nil {
		return result, fmt.Errorf(
			"could not write the admin PAT to %q before commit: %w", cfg.PATFile, err,
		)
	}
	result.PATPath = cfg.PATFile
	return result, nil
}

// discardPublishedFile removes a PAT that could not be made durable. A failed
// removal is reported separately so the operator knows a stale file remains.
func discardPublishedFile(path string, cause error) error {
	if err := removeFile(path); err != nil && !errors.Is(err, os.ErrNotExist) {
		return fmt.Errorf("%w (and the published file %q could not be removed: %v)", cause, path, err)
	}
	return cause
}

// removeFile deletes a published PAT. It is a variable so the removal-failure
// path can be tested.
var removeFile = os.Remove

// syncDir flushes the directory entry after the rename. It is a variable so the
// failure path, which must not leave a retrievable credential, can be tested.
var syncDir = func(handle *os.File) error { return handle.Sync() }

// writeRestrictedFile creates the destination atomically with mode 0600.
//
// Writing a temporary file in the destination directory and renaming it means
// the final mode never depends on a pre-existing file (os.WriteFile would keep
// a 0644 file's permissions), and a symlink at the destination is replaced
// rather than followed.
func writeRestrictedFile(path, value string) error {
	dir := filepath.Dir(path)
	tmp, err := os.CreateTemp(dir, ".ibex-secret-*")
	if err != nil {
		return err
	}
	tmpName := tmp.Name()
	defer func() { _ = os.Remove(tmpName) }()

	// os.CreateTemp creates the file with mode 0600. Writing here and renaming
	// below means a pre-existing 0644 destination is replaced, not reused.
	if _, err := tmp.WriteString(value + "\n"); err != nil {
		_ = tmp.Close()
		return err
	}
	if err := tmp.Sync(); err != nil {
		_ = tmp.Close()
		return err
	}
	if err := tmp.Close(); err != nil {
		return err
	}
	if err := os.Rename(tmpName, path); err != nil {
		return err
	}
	dirHandle, err := os.Open(dir)
	if err != nil {
		return discardPublishedFile(path, err)
	}
	defer func() { _ = dirHandle.Close() }()
	if err := syncDir(dirHandle); err != nil {
		// The rename already published the file. Remove it so a failed delivery
		// cannot leave a credential the rolled-back transaction never issued.
		return discardPublishedFile(path, fmt.Errorf(
			"sync the PAT directory %q: %w (the filesystem must support directory fsync)", dir, err,
		))
	}
	return nil
}

// loadBootstrapConfig reads and validates the bootstrap inputs.
func loadBootstrapConfig(getenv func(string) string) (bootstrapConfig, error) {
	cfg := bootstrapConfig{
		PostgresDSN: strings.TrimSpace(getenv("POSTGRES_DSN")),
		OrgName:     envOrDefault(getenv, "IBEX_BOOTSTRAP_ORG_NAME", defaultOrgName),
		OrgSlug:     envOrDefault(getenv, "IBEX_BOOTSTRAP_ORG_SLUG", defaultOrgSlug),
		UserEmail:   envOrDefault(getenv, "IBEX_BOOTSTRAP_USER_EMAIL", defaultUserEmail),
		UserName:    envOrDefault(getenv, "IBEX_BOOTSTRAP_USER_NAME", defaultUserName),
		AgentName:   envOrDefault(getenv, "IBEX_BOOTSTRAP_AGENT_NAME", defaultAgentName),
		AgentSlug:   envOrDefault(getenv, "IBEX_BOOTSTRAP_AGENT_SLUG", defaultAgentSlug),
		PATName:     envOrDefault(getenv, "IBEX_BOOTSTRAP_PAT_NAME", defaultPATName),
		PATFile:     strings.TrimSpace(getenv("IBEX_BOOTSTRAP_PAT_FILE")),
		MemoryToken: strings.TrimSpace(getenv("IBEX_MEMORY_API_TOKEN")),
	}
	if err := cfg.validate(); err != nil {
		return bootstrapConfig{}, err
	}
	return cfg, nil
}

func envOrDefault(getenv func(string) string, key, fallback string) string {
	if value := strings.TrimSpace(getenv(key)); value != "" {
		return value
	}
	return fallback
}

func (c bootstrapConfig) validate() error {
	if err := c.validateIdentity(); err != nil {
		return err
	}
	return c.validateOutput()
}

// validateIdentity checks the values that become database rows.
func (c bootstrapConfig) validateIdentity() error {
	if c.PostgresDSN == "" {
		return errors.New("POSTGRES_DSN is required")
	}
	if !slugPattern.MatchString(c.OrgSlug) {
		return fmt.Errorf("IBEX_BOOTSTRAP_ORG_SLUG %q must match %s", c.OrgSlug, slugPattern)
	}
	if !slugPattern.MatchString(c.AgentSlug) {
		return fmt.Errorf("IBEX_BOOTSTRAP_AGENT_SLUG %q must match %s", c.AgentSlug, slugPattern)
	}
	if !emailPattern.MatchString(c.UserEmail) {
		return fmt.Errorf("IBEX_BOOTSTRAP_USER_EMAIL %q must match %s", c.UserEmail, emailPattern)
	}
	if c.MemoryToken == "" {
		return nil
	}
	if _, err := token.ParsePAT(c.MemoryToken); err != nil {
		return fmt.Errorf(
			"IBEX_MEMORY_API_TOKEN must be a PAT-shaped ibex_pat_<uuid>_<secret> value: %w",
			err,
		)
	}
	return nil
}

// validateOutput checks that the credential can be delivered before any row is
// committed.
func (c bootstrapConfig) validateOutput() error {
	if c.PATFile == "" {
		return errors.New(
			"IBEX_BOOTSTRAP_PAT_FILE is required: the admin PAT is written to a file, never to stdout",
		)
	}
	info, err := os.Stat(filepath.Dir(c.PATFile))
	if err != nil || !info.IsDir() {
		return fmt.Errorf("IBEX_BOOTSTRAP_PAT_FILE %q must name a file in an existing directory", c.PATFile)
	}
	return nil
}

// bootstrapPermissions is the exact bootstrap PAT grant:
// Admin | SecretUse | OperatorMetadataRead.
func bootstrapPermissions() int64 {
	return permissions.Admin | permissions.SecretUse | permissions.OperatorMetadataRead
}

// bootstrap runs the identity, policy, PAT, and memory-token writes in one
// transaction. Every statement is a SECURITY DEFINER call, so the command needs
// no table privilege and no tenant GUC: inside the definer current_user is
// ibex_service, which the tenant policy admits.
func bootstrap(ctx context.Context, db *sql.DB, cfg bootstrapConfig) (bootstrapResult, error) {
	ctx, cancel := context.WithTimeout(ctx, bootstrapTimeout)
	defer cancel()

	tx, err := db.BeginTx(ctx, nil)
	if err != nil {
		return bootstrapResult{}, fmt.Errorf("begin bootstrap transaction: %w", err)
	}
	defer func() { _ = tx.Rollback() }()

	result, err := bootstrapInTx(ctx, tx, cfg)
	if err != nil {
		return bootstrapResult{}, err
	}
	result, err = deliverBootstrapPAT(cfg, result)
	if err != nil {
		return bootstrapResult{}, err
	}
	if err := tx.Commit(); err != nil {
		return bootstrapResult{}, fmt.Errorf("commit bootstrap transaction: %w", err)
	}
	return result, nil
}

// bootstrapInTx decides between a first-run identity and an existing-org
// reconcile. It never creates a second organization or rotates the PAT.
func bootstrapInTx(ctx context.Context, tx *sql.Tx, cfg bootstrapConfig) (bootstrapResult, error) {
	orgID := uuid.New()
	result, err := insertOrganization(ctx, tx, orgInput{id: orgID, cfg: cfg})
	if err != nil {
		return bootstrapResult{}, err
	}
	if result.AlreadyBootstrapped {
		return reconcileExisting(ctx, tx, cfg, result)
	}
	return createIdentity(ctx, tx, cfg, orgID)
}

// reconcileExisting updates the memory token for an already-bootstrapped organization.
func reconcileExisting(
	ctx context.Context,
	tx *sql.Tx,
	cfg bootstrapConfig,
	result bootstrapResult,
) (bootstrapResult, error) {
	if cfg.MemoryToken == "" {
		return result, nil
	}
	if err := reconcileServiceToken(ctx, tx, result.OrgID, cfg.MemoryToken); err != nil {
		return bootstrapResult{}, err
	}
	result.MemoryTokenManaged = true
	return result, nil
}

// createIdentity writes the first-run user, agent, PAT, and memory token. The
// allow-all model policy is not written here: insertOrganization writes it in
// the statement that created the organization.
func createIdentity(
	ctx context.Context,
	tx *sql.Tx,
	cfg bootstrapConfig,
	orgID uuid.UUID,
) (bootstrapResult, error) {
	userID, agentID, err := insertIdentity(ctx, tx, identityInput{orgID: orgID, cfg: cfg})
	if err != nil {
		return bootstrapResult{}, err
	}
	plaintext, err := insertToken(ctx, tx, tokenInput{
		orgID: orgID, userID: userID, agentID: agentID, name: cfg.PATName,
	})
	if err != nil {
		return bootstrapResult{}, err
	}
	memoryManaged := false
	if cfg.MemoryToken != "" {
		in := serviceTokenInput{orgID: orgID, bearer: cfg.MemoryToken}
		if err := writeServiceToken(ctx, tx, in); err != nil {
			return bootstrapResult{}, err
		}
		memoryManaged = true
	}
	return bootstrapResult{
		OrgID: orgID, UserID: userID, AgentID: agentID,
		PAT: plaintext, MemoryTokenManaged: memoryManaged,
	}, nil
}

// reconcileServiceToken resolves the existing owner and agent and writes the
// scoped token without touching any PAT. It is used only for an already
// bootstrapped organization.
func reconcileServiceToken(ctx context.Context, tx *sql.Tx, orgID uuid.UUID, bearer string) error {
	locked, err := lockOrganization(ctx, tx, orgID)
	if err != nil {
		return fmt.Errorf("lock organization for memory token: %w", err)
	}
	if !locked {
		return fmt.Errorf(
			"lock organization for memory token: organization %s is missing or soft-deleted",
			orgID,
		)
	}
	subjects, err := lookupSubjects(ctx, tx, orgID)
	if err != nil {
		return fmt.Errorf("look up owner and agent for memory token: %w", err)
	}
	if !subjects.owner.Valid {
		return fmt.Errorf(
			"organization %s has no active owner; cannot bind the memory service token to a subject",
			orgID,
		)
	}
	if !subjects.agent.Valid {
		return fmt.Errorf(
			"organization %s has no active agent; create one before starting the profile, "+
				"otherwise the memory service token would be accepted for any agent",
			orgID,
		)
	}
	return writeServiceToken(ctx, tx, serviceTokenInput{orgID: orgID, bearer: bearer})
}

// lookupSubjects returns the organization's active owner and default agent.
func lookupSubjects(ctx context.Context, tx *sql.Tx, orgID uuid.UUID) (subjectIDs, error) {
	var subjects subjectIDs
	if err := tx.QueryRowContext(ctx, lookupSubjectsSQL, orgID.String()).
		Scan(&subjects.owner, &subjects.agent); err != nil {
		return subjectIDs{}, err
	}
	return subjects, nil
}

// lockOrganization serializes memory-token reconciliation for one organization
// and reports whether a non-deleted row exists to reconcile.
func lockOrganization(ctx context.Context, tx *sql.Tx, orgID uuid.UUID) (bool, error) {
	var locked bool
	if err := tx.QueryRowContext(ctx, lockOrganizationSQL, orgID.String()).Scan(&locked); err != nil {
		return false, err
	}
	return locked, nil
}

// writeServiceToken inserts or updates the org's scoped memory service token.
// The wire value is supplied by the operator/secret generator; only the
// Argon2id hash is stored. Updating an existing row makes rotation effective
// and invalidates the previous value.
//
// One definer performs the whole reconcile — prefix ownership, the managed-row
// find, the update or insert, and the duplicate revoke — and reports which
// branch it took, because the refusal text belongs to the operator, not to SQL.
func writeServiceToken(ctx context.Context, tx *sql.Tx, in serviceTokenInput) error {
	parsed, err := token.ParsePAT(in.bearer)
	if err != nil {
		return fmt.Errorf("parse memory service token: %w", err)
	}
	hash, err := crypto.HashToken(in.bearer, crypto.ProductionParams())
	if err != nil {
		return fmt.Errorf("hash memory service token: %w", err)
	}
	perms := permissions.MemoryRead | permissions.MemoryWrite
	var outcome string
	var tokenID uuid.NullUUID
	if err := tx.QueryRowContext(ctx, upsertServiceTokenSQL,
		in.orgID.String(), hash, parsed.Prefix, perms,
	).Scan(&outcome, &tokenID); err != nil {
		return fmt.Errorf("write memory service token: %w", err)
	}
	return serviceTokenOutcome(outcome, in.orgID)
}

// serviceTokenOutcome maps a definer outcome to the operator-facing error, or
// nil for the two outcomes that wrote the row the operator asked for.
func serviceTokenOutcome(outcome string, orgID uuid.UUID) error {
	switch outcome {
	case outcomeInserted, outcomeUpdated:
		return nil
	case outcomePrefixConflict:
		return errors.New(
			"the memory service token is already bound to another organization; " +
				"use a distinct IBEX_MEMORY_API_TOKEN",
		)
	case outcomeRevokedRefused:
		// Never resurrect a credential the operator revoked. Failing the
		// one-shot makes the state visible instead of silently re-enabling the
		// old grant.
		return fmt.Errorf(
			"memory-service token for org %s is revoked; refusing to reactivate it; "+
				"delete the row or issue a new token before starting the profile",
			orgID,
		)
	default:
		return fmt.Errorf("write memory service token: unrecognised outcome %q", outcome)
	}
}

// insertOrganization upserts by slug so two concurrent bootstraps cannot create
// a second organization. On the created branch the same definer writes the
// allow-all model policy and epoch 1: the policy is part of the creation, so a
// caller that names an existing slug receives created = false and no policy row,
// and a policy failure fails this call and rolls the transaction back. It
// reports the existing ID without touching a token when the slug is already
// present, and names a soft-deleted winner instead of surfacing a bare no-rows
// error.
func insertOrganization(
	ctx context.Context,
	tx *sql.Tx,
	in orgInput,
) (bootstrapResult, error) {
	var created bool
	var orgID uuid.UUID
	var deletedAt sql.NullTime
	if err := tx.QueryRowContext(ctx, upsertOrganizationSQL,
		in.id.String(), in.cfg.OrgName, in.cfg.OrgSlug,
	).Scan(&created, &orgID, &deletedAt); err != nil {
		return bootstrapResult{}, fmt.Errorf("insert organization: %w", err)
	}
	if created {
		return bootstrapResult{}, nil
	}
	if deletedAt.Valid {
		return bootstrapResult{}, fmt.Errorf(
			"organization slug %q belongs to a soft-deleted organization (%s); "+
				"hard-delete it or choose another IBEX_BOOTSTRAP_ORG_SLUG",
			in.cfg.OrgSlug, orgID,
		)
	}
	return bootstrapResult{AlreadyBootstrapped: true, OrgID: orgID}, nil
}

// insertIdentity creates the owner user and the default agent in one definer
// call, so the agent's created_by is the user created alongside it.
func insertIdentity(
	ctx context.Context,
	tx *sql.Tx,
	in identityInput,
) (uuid.UUID, uuid.UUID, error) {
	userID := uuid.New()
	agentID := uuid.New()
	if err := tx.QueryRowContext(ctx, createIdentitySQL,
		in.orgID.String(), userID.String(), in.cfg.UserEmail, in.cfg.UserName,
		agentID.String(), in.cfg.AgentName, in.cfg.AgentSlug,
	).Scan(&userID, &agentID); err != nil {
		return uuid.Nil, uuid.Nil, fmt.Errorf("insert owner user and default agent: %w", err)
	}
	return userID, agentID, nil
}

// insertToken writes the bootstrap PAT and returns its one-time wire value.
func insertToken(
	ctx context.Context,
	tx *sql.Tx,
	in tokenInput,
) (string, error) {
	plaintext, prefix, rowID, err := token.GeneratePAT()
	if err != nil {
		return "", fmt.Errorf("generate bootstrap PAT: %w", err)
	}
	hash, err := crypto.HashToken(plaintext, crypto.ProductionParams())
	if err != nil {
		return "", fmt.Errorf("hash bootstrap PAT: %w", err)
	}
	// The definer echoes the id Go generated; nothing reads it.
	if _, err := tx.ExecContext(ctx, insertPATSQL,
		rowID.String(), in.orgID.String(), in.userID.String(), in.agentID.String(),
		hash, prefix, in.name, bootstrapPermissions(),
	); err != nil {
		return "", fmt.Errorf("insert bootstrap PAT: %w", err)
	}
	return plaintext, nil
}

// printBootstrapResult writes the operator summary and reports a delivery failure.
func printBootstrapResult(w io.Writer, result bootstrapResult) error {
	var b strings.Builder
	if result.AlreadyBootstrapped {
		writeAlreadyBootstrapped(&b, result)
	} else {
		writeBootstrapComplete(&b, result)
	}
	_, err := io.WriteString(w, b.String())
	return err
}

// writeAlreadyBootstrapped writes the idempotent-rerun summary.
func writeAlreadyBootstrapped(b *strings.Builder, result bootstrapResult) {
	writef(b, "already bootstrapped: organization %s exists; no organization or PAT was created\n", result.OrgID)
	if result.MemoryTokenManaged {
		writef(b, "memory service token: service_token row updated from IBEX_MEMORY_API_TOKEN\n")
	}
}

// writeBootstrapComplete writes the first-run summary.
func writeBootstrapComplete(b *strings.Builder, result bootstrapResult) {
	writef(b, "\n")
	writef(b, "%s", bootstrapBanner)
	writef(b, " IBEX BOOTSTRAP COMPLETE\n")
	writef(b, "%s", bootstrapBanner)
	writef(b, " Organization: %s\n", result.OrgID)
	writef(b, " Owner user:   %s\n", result.UserID)
	writef(b, " Agent:        %s\n", result.AgentID)
	if result.MemoryTokenManaged {
		writef(b, " Memory token: service_token row created or updated from IBEX_MEMORY_API_TOKEN\n")
	}
	writef(b, "%s", bootstrapRule)
	writePATSection(b, result)
	writef(b, "%s", bootstrapRule)
	writeRecoveryNote(b, result)
	writef(b, "%s", bootstrapBanner)
	writef(b, "\n")
}

// writePATSection writes the PAT file path. The value itself is never printed:
// a container or CI log would retain it.
func writePATSection(b *strings.Builder, result bootstrapResult) {
	if result.PATPath != "" {
		writef(b, " IBEX_BOOTSTRAP_PAT_FILE=%s\n", result.PATPath)
	}
}

// writeRecoveryNote explains how to retrieve the PAT from its file.
func writeRecoveryNote(b *strings.Builder, result bootstrapResult) {
	if result.PATPath != "" {
		writef(b, " Retrieve it with make v1-bootstrap-pat, then delete the file.\n")
	}
	writef(b, " Store it in your secret manager now. Only its Argon2id hash is stored.\n")
}

// writef writes a formatted summary line and discards the builder-only error.
func writef(w io.Writer, format string, args ...any) {
	_, _ = fmt.Fprintf(w, format, args...)
}
