// Command bootstrap creates the first v1-single-node organization, owner user,
// default agent, allow-all model policy, and a bootstrap PAT in one transaction.
// It is idempotent per organization slug, never rotates the PAT, and reconciles
// the scoped memory service token without reactivating a revoked row.
package main

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"io"
	"os"
	"regexp"
	"strings"
	"time"

	"github.com/Rick1330/ibex-harness/packages/crypto"
	"github.com/Rick1330/ibex-harness/packages/permissions"
	"github.com/Rick1330/ibex-harness/services/auth/internal/token"
	"github.com/google/uuid"
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

	bootstrapBanner = "======================================================================\n"
	bootstrapRule   = "----------------------------------------------------------------------\n"
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
	orgID   uuid.UUID
	userID  uuid.NullUUID
	agentID uuid.NullUUID
	bearer  string
}

type serviceTokenRow struct {
	id      uuid.UUID
	orgID   uuid.UUID
	prefix  string
	hash    string
	revoked bool
}

const (
	ownerLookupSQL = `SELECT id FROM ibex_core.users
		WHERE org_id = $1 AND role = 'owner'
		ORDER BY created_at LIMIT 1`
	agentLookupSQL = `SELECT id FROM ibex_core.agents
		WHERE org_id = $1
		ORDER BY created_at LIMIT 1`
	serviceTokenLookupSQL = `SELECT id, is_revoked FROM ibex_core.tokens
		WHERE org_id = $1 AND type = 'service_token' AND name = 'memory-service'
		ORDER BY created_at LIMIT 1`
)

func main() {
	os.Exit(run(os.Stdout, os.Stderr, os.Getenv))
}

func run(stdout, stderr io.Writer, getenv func(string) string) int {
	cfg, err := loadBootstrapConfig(getenv)
	if err != nil {
		writef(stderr, "ibex-bootstrap: %v\n", err)
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
		writef(stderr, "ibex-bootstrap: %v\n", err)
		return 1
	}
	printBootstrapResult(stdout, result)
	return 0
}

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
	if c.MemoryToken != "" {
		if _, err := token.ParsePAT(c.MemoryToken); err != nil {
			return fmt.Errorf(
				"IBEX_MEMORY_API_TOKEN must be a PAT-shaped ibex_pat_<uuid>_<secret> value: %w",
				err,
			)
		}
	}
	return nil
}

// bootstrapPermissions is the exact bootstrap PAT grant:
// Admin | SecretUse | OperatorMetadataRead.
func bootstrapPermissions() int64 {
	return permissions.Admin | permissions.SecretUse | permissions.OperatorMetadataRead
}

func bootstrap(ctx context.Context, db *sql.DB, cfg bootstrapConfig) (bootstrapResult, error) {
	ctx, cancel := context.WithTimeout(ctx, bootstrapTimeout)
	defer cancel()

	tx, err := db.BeginTx(ctx, nil)
	if err != nil {
		return bootstrapResult{}, fmt.Errorf("begin bootstrap transaction: %w", err)
	}
	defer func() { _ = tx.Rollback() }()

	if _, err := tx.ExecContext(ctx, `SELECT set_config('app.is_service_account', 'true', true)`); err != nil {
		return bootstrapResult{}, fmt.Errorf("set service-account session: %w", err)
	}

	result, err := bootstrapInTx(ctx, tx, cfg)
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
	if err := insertModelPolicy(ctx, tx, orgID); err != nil {
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
		in := serviceTokenInput{
			orgID:   orgID,
			userID:  uuid.NullUUID{UUID: userID, Valid: true},
			agentID: uuid.NullUUID{UUID: agentID, Valid: true},
			bearer:  cfg.MemoryToken,
		}
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
	userID, err := lookupNullableID(ctx, tx, ownerLookupSQL, orgID)
	if err != nil {
		return fmt.Errorf("look up owner for memory token: %w", err)
	}
	agentID, err := lookupNullableID(ctx, tx, agentLookupSQL, orgID)
	if err != nil {
		return fmt.Errorf("look up agent for memory token: %w", err)
	}
	in := serviceTokenInput{orgID: orgID, userID: userID, agentID: agentID, bearer: bearer}
	return writeServiceToken(ctx, tx, in)
}

func lookupNullableID(
	ctx context.Context,
	tx *sql.Tx,
	query string,
	orgID uuid.UUID,
) (uuid.NullUUID, error) {
	var id uuid.NullUUID
	err := tx.QueryRowContext(ctx, query, orgID.String()).Scan(&id)
	if errors.Is(err, sql.ErrNoRows) {
		return uuid.NullUUID{}, nil
	}
	if err != nil {
		return uuid.NullUUID{}, err
	}
	return id, nil
}

// writeServiceToken inserts or updates the org's scoped memory service token.
// The wire value is supplied by the operator/secret generator; only the
// Argon2id hash is stored. Updating an existing row makes rotation effective
// and invalidates the previous value.
func writeServiceToken(ctx context.Context, tx *sql.Tx, in serviceTokenInput) error {
	parsed, err := token.ParsePAT(in.bearer)
	if err != nil {
		return fmt.Errorf("parse memory service token: %w", err)
	}
	hash, err := crypto.HashToken(in.bearer, crypto.ProductionParams())
	if err != nil {
		return fmt.Errorf("hash memory service token: %w", err)
	}
	row, err := findServiceToken(ctx, tx, in.orgID)
	switch {
	case err == nil:
		row.prefix = parsed.Prefix
		row.hash = hash
		return updateServiceToken(ctx, tx, row)
	case errors.Is(err, sql.ErrNoRows):
		return insertServiceToken(ctx, tx, in, serviceTokenRow{prefix: parsed.Prefix, hash: hash})
	default:
		return fmt.Errorf("look up memory service token: %w", err)
	}
}

func findServiceToken(
	ctx context.Context,
	tx *sql.Tx,
	orgID uuid.UUID,
) (serviceTokenRow, error) {
	var row serviceTokenRow
	err := tx.QueryRowContext(ctx, serviceTokenLookupSQL, orgID.String()).
		Scan(&row.id, &row.revoked)
	row.orgID = orgID
	return row, err
}

func updateServiceToken(ctx context.Context, tx *sql.Tx, row serviceTokenRow) error {
	if row.revoked {
		// Never resurrect a credential the operator revoked. Failing the
		// one-shot makes the state visible instead of silently re-enabling the
		// old grant.
		return fmt.Errorf(
			"memory-service token for org %s is revoked; refusing to reactivate it; "+
				"delete the row or issue a new token before starting the profile",
			row.orgID,
		)
	}
	perms := permissions.MemoryRead | permissions.MemoryWrite
	if _, err := tx.ExecContext(ctx, `
		UPDATE ibex_core.tokens
		SET hash = $2, prefix = $3, permissions = $4, updated_at = NOW()
		WHERE id = $1`,
		row.id.String(), row.hash, row.prefix, perms,
	); err != nil {
		return fmt.Errorf("update memory service token: %w", err)
	}
	return nil
}

func insertServiceToken(
	ctx context.Context,
	tx *sql.Tx,
	in serviceTokenInput,
	row serviceTokenRow,
) error {
	perms := permissions.MemoryRead | permissions.MemoryWrite
	if _, err := tx.ExecContext(ctx, `
		INSERT INTO ibex_core.tokens
			(id, org_id, user_id, agent_id, type, hash, prefix, name,
			 permissions, is_revoked, expires_at)
		VALUES ($1, $2, $3, $4, 'service_token', $5, $6, 'memory-service',
			$7, false, NULL)`,
		uuid.New().String(), in.orgID.String(), in.userID, in.agentID,
		row.hash, row.prefix, perms,
	); err != nil {
		return fmt.Errorf("insert memory service token: %w", err)
	}
	return nil
}

// insertOrganization uses ON CONFLICT (slug) DO NOTHING so two concurrent
// bootstraps cannot create a second organization. It reports the existing ID
// without touching a token when the slug is already present.
func insertOrganization(
	ctx context.Context,
	tx *sql.Tx,
	in orgInput,
) (bootstrapResult, error) {
	result, err := tx.ExecContext(ctx, `
		INSERT INTO ibex_core.organizations
			(id, name, slug, tier, status,
			 embedding_profile, embedding_dim, embedding_model_id)
		VALUES ($1, $2, $3, 'free', 'active', 'gpu', 1024, 'BAAI/bge-m3')
		ON CONFLICT (slug) DO NOTHING`,
		in.id.String(), in.cfg.OrgName, in.cfg.OrgSlug)
	if err != nil {
		return bootstrapResult{}, fmt.Errorf("insert organization: %w", err)
	}
	rows, err := result.RowsAffected()
	if err != nil {
		return bootstrapResult{}, fmt.Errorf("organization insert result: %w", err)
	}
	if rows > 0 {
		return bootstrapResult{}, nil
	}

	var existing uuid.UUID
	if err := tx.QueryRowContext(ctx,
		`SELECT id FROM ibex_core.organizations WHERE slug = $1`, in.cfg.OrgSlug,
	).Scan(&existing); err != nil {
		return bootstrapResult{}, fmt.Errorf("look up existing organization: %w", err)
	}
	return bootstrapResult{AlreadyBootstrapped: true, OrgID: existing}, nil
}

// insertIdentity creates the owner user and the default agent in one helper so
// the two inserts stay together and the first-run path stays short.
func insertIdentity(
	ctx context.Context,
	tx *sql.Tx,
	in identityInput,
) (uuid.UUID, uuid.UUID, error) {
	userID := uuid.New()
	if _, err := tx.ExecContext(ctx, `
		INSERT INTO ibex_core.users (id, org_id, email, name, role, status)
		VALUES ($1, $2, $3, $4, 'owner', 'active')`,
		userID.String(), in.orgID.String(), in.cfg.UserEmail, in.cfg.UserName,
	); err != nil {
		return uuid.Nil, uuid.Nil, fmt.Errorf("insert owner user: %w", err)
	}

	agentID := uuid.New()
	if _, err := tx.ExecContext(ctx, `
		INSERT INTO ibex_core.agents (id, org_id, created_by, name, slug, status)
		VALUES ($1, $2, $3, $4, $5, 'active')`,
		agentID.String(), in.orgID.String(), userID.String(), in.cfg.AgentName, in.cfg.AgentSlug,
	); err != nil {
		return uuid.Nil, uuid.Nil, fmt.Errorf("insert agent: %w", err)
	}
	return userID, agentID, nil
}

// insertModelPolicy writes the allow-all fallback policy and its epoch, which
// matches infra/scripts/seed_dev.sql.
func insertModelPolicy(ctx context.Context, tx *sql.Tx, orgID uuid.UUID) error {
	if _, err := tx.ExecContext(ctx, `
		INSERT INTO ibex_core.org_model_policies (org_id, model_pattern, allowed, priority)
		VALUES ($1, '*', true, 1000)`,
		orgID.String(),
	); err != nil {
		return fmt.Errorf("insert allow-all model policy: %w", err)
	}
	if _, err := tx.ExecContext(ctx, `
		INSERT INTO ibex_core.org_model_policy_meta (org_id, epoch)
		VALUES ($1, 1)`,
		orgID.String(),
	); err != nil {
		return fmt.Errorf("insert model policy epoch: %w", err)
	}
	return nil
}

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
	if _, err := tx.ExecContext(ctx, `
		INSERT INTO ibex_core.tokens
			(id, org_id, user_id, agent_id, type, hash, prefix, name,
			 permissions, is_revoked, expires_at)
		VALUES ($1, $2, $3, $4, 'pat', $5, $6, $7, $8, false, NULL)`,
		rowID.String(), in.orgID.String(), in.userID.String(), in.agentID.String(),
		hash, prefix, in.name, bootstrapPermissions(),
	); err != nil {
		return "", fmt.Errorf("insert bootstrap PAT: %w", err)
	}
	return plaintext, nil
}

func printBootstrapResult(w io.Writer, result bootstrapResult) {
	if result.AlreadyBootstrapped {
		writef(w, "already bootstrapped: organization %s exists; no organization or PAT was created\n", result.OrgID)
		if result.MemoryTokenManaged {
			writef(w, "memory service token: service_token row updated from IBEX_MEMORY_API_TOKEN\n")
		}
		return
	}
	writef(w, "\n")
	writef(w, "%s", bootstrapBanner)
	writef(w, " IBEX BOOTSTRAP COMPLETE\n")
	writef(w, "%s", bootstrapBanner)
	writef(w, " Organization: %s\n", result.OrgID)
	writef(w, " Owner user:   %s\n", result.UserID)
	writef(w, " Agent:        %s\n", result.AgentID)
	if result.MemoryTokenManaged {
		writef(w, " Memory token: service_token row created or updated from IBEX_MEMORY_API_TOKEN\n")
	}
	writef(w, "%s", bootstrapRule)
	writef(w, " IBEX_BOOTSTRAP_PAT=%s\n", result.PAT)
	writef(w, "%s", bootstrapRule)
	writef(w, " WARNING: this PAT is shown once and cannot be recovered.\n")
	writef(w, " Store it in your secret manager now. Only its Argon2id hash is stored.\n")
	writef(w, "%s", bootstrapBanner)
	writef(w, "\n")
}

func writef(w io.Writer, format string, args ...any) {
	_, _ = fmt.Fprintf(w, format, args...)
}
