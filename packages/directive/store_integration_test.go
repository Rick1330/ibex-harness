//go:build integration

package directive_test

import (
	"context"
	"database/sql"
	"os"
	"testing"
	"time"

	migratepg "github.com/Rick1330/ibex-harness/infra/migrations/postgres"
	"github.com/Rick1330/ibex-harness/packages/directive"
	"github.com/alicebob/miniredis/v2"
	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
	"github.com/stretchr/testify/require"

	// Register the lib/pq "postgres" driver for sql.Open in integration tests.
	_ "github.com/lib/pq"
)

const defaultTestDSN = "postgres://ibex:ibex@localhost:5433/ibex_test?sslmode=disable"

const (
	seedInsertOrgSQL = `
		INSERT INTO ibex_core.organizations (name, slug)
		VALUES ($1, $2) RETURNING id::text`
	seedInsertUserSQL = `
		INSERT INTO ibex_core.users (org_id, email, name)
		VALUES ($1::uuid, $2, $3) RETURNING id::text`
	seedInsertAgentSQL = `
		INSERT INTO ibex_core.agents (org_id, created_by, name, slug)
		VALUES ($1::uuid, $2::uuid, $3, $4) RETURNING id::text`
	seedInsertDirectiveSQL = `
		INSERT INTO ibex_core.directives (org_id, agent_id)
		VALUES ($1::uuid, $2::uuid) RETURNING id::text`
	seedInsertVersionSQL = `
		INSERT INTO ibex_core.directive_versions
			(directive_id, org_id, version_num, content, content_hash)
		VALUES ($1::uuid, $2::uuid, 1, $3, $4) RETURNING id::text`
	seedActivateVersionSQL = `
		UPDATE ibex_core.directives
		SET active_version_id = $1::uuid
		WHERE id = $2::uuid AND org_id = $3::uuid`
)

func integrationDSN() string {
	if dsn := os.Getenv("POSTGRES_TEST_DSN"); dsn != "" {
		return dsn
	}
	return defaultTestDSN
}

func openIntegrationDB(t *testing.T) (*sql.DB, string) {
	t.Helper()
	dsn := integrationDSN()
	db, err := sql.Open("postgres", dsn)
	if err != nil {
		t.Fatalf("open db: %v", err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := db.PingContext(ctx); err != nil {
		t.Skipf("postgres not available: %v", err)
	}
	resetIntegrationSchema(t, db)
	if err := migratepg.Up(dsn); err != nil {
		t.Fatalf("migrate up: %v", err)
	}
	return db, dsn
}

func resetIntegrationSchema(t *testing.T, db *sql.DB) {
	t.Helper()
	ctx := context.Background()
	_, _ = db.ExecContext(ctx, `DROP SCHEMA IF EXISTS ibex_core CASCADE`)
	_, _ = db.ExecContext(ctx, `DROP TABLE IF EXISTS schema_migrations`)
	_, _ = db.ExecContext(ctx, `DROP ROLE IF EXISTS ibex_app`)
}

type seededAgentDirective struct {
	orgID   uuid.UUID
	agentID uuid.UUID
	content string
}

type agentDirectiveSeed struct {
	db                        *sql.DB
	orgName, orgSlug, content string
}

func seedAgentDirective(t *testing.T, seed agentDirectiveSeed) seededAgentDirective {
	t.Helper()
	ctx := context.Background()
	var ids seedIDs
	err := withServiceAccount(ctx, seed.db, func(tx *sql.Tx) error {
		return insertSeededDirective(ctx, tx, seed, &ids)
	})
	if err != nil {
		t.Fatalf("seed: %v", err)
	}
	return seededAgentDirective{
		orgID:   uuid.MustParse(ids.orgID),
		agentID: uuid.MustParse(ids.agentID),
		content: seed.content,
	}
}

type seedIDs struct {
	orgID, userID, agentID, directiveID, versionID string
}

func insertSeededDirective(ctx context.Context, tx *sql.Tx, seed agentDirectiveSeed, ids *seedIDs) error {
	if err := tx.QueryRowContext(ctx, seedInsertOrgSQL, seed.orgName, seed.orgSlug).Scan(&ids.orgID); err != nil {
		return err
	}
	if err := tx.QueryRowContext(ctx, seedInsertUserSQL,
		ids.orgID, seed.orgSlug+"@example.com", seed.orgName+" User").Scan(&ids.userID); err != nil {
		return err
	}
	if err := tx.QueryRowContext(ctx, seedInsertAgentSQL,
		ids.orgID, ids.userID, seed.orgName+" Agent", seed.orgSlug+"-agent").Scan(&ids.agentID); err != nil {
		return err
	}
	if err := tx.QueryRowContext(ctx, seedInsertDirectiveSQL, ids.orgID, ids.agentID).Scan(&ids.directiveID); err != nil {
		return err
	}
	if err := tx.QueryRowContext(ctx, seedInsertVersionSQL,
		ids.directiveID, ids.orgID, seed.content, "hash-"+seed.content).Scan(&ids.versionID); err != nil {
		return err
	}
	return activateSeededVersion(ctx, tx, ids)
}

func activateSeededVersion(ctx context.Context, tx *sql.Tx, ids *seedIDs) error {
	res, err := tx.ExecContext(ctx, seedActivateVersionSQL, ids.versionID, ids.directiveID, ids.orgID)
	if err != nil {
		return err
	}
	n, err := res.RowsAffected()
	if err != nil {
		return err
	}
	if n != 1 {
		return sql.ErrNoRows
	}
	return nil
}

func withServiceAccount(ctx context.Context, db *sql.DB, fn func(*sql.Tx) error) error {
	tx, err := db.BeginTx(ctx, nil)
	if err != nil {
		return err
	}
	defer func() { _ = tx.Rollback() }()
	if _, err := tx.ExecContext(ctx, `SELECT set_config('app.is_service_account', 'true', true)`); err != nil {
		return err
	}
	if err := fn(tx); err != nil {
		return err
	}
	return tx.Commit()
}

func TestIntegration_PostgresStore_Load(t *testing.T) {
	db, _ := openIntegrationDB(t)
	defer db.Close()

	seeded := seedAgentDirective(t, agentDirectiveSeed{db: db, orgName: "Org A", orgSlug: "org-a", content: "Be concise and safe."})
	store, err := directive.NewPostgresStore(db)
	if err != nil {
		t.Fatalf("store: %v", err)
	}

	got, err := store.Load(context.Background(), seeded.orgID, seeded.agentID)
	if err != nil {
		t.Fatalf("load: %v", err)
	}
	if got.Content != seeded.content {
		t.Fatalf("content=%q want %q", got.Content, seeded.content)
	}
	if got.InjectionMode != directive.DefaultInjectionMode {
		t.Fatalf("mode=%q", got.InjectionMode)
	}
	if got.VersionID == uuid.Nil {
		t.Fatal("expected version id")
	}

	empty, err := store.Load(context.Background(), seeded.orgID, uuid.New())
	if err != nil {
		t.Fatalf("empty load: %v", err)
	}
	if empty.HasContent() {
		t.Fatalf("expected empty for unknown agent: %+v", empty)
	}
}

func TestIntegration_PostgresStore_CrossTenantDenied(t *testing.T) {
	db, _ := openIntegrationDB(t)
	defer db.Close()

	orgA := seedAgentDirective(t, agentDirectiveSeed{db: db, orgName: "Org A", orgSlug: "org-a", content: "directive-a"})
	orgB := seedAgentDirective(t, agentDirectiveSeed{db: db, orgName: "Org B", orgSlug: "org-b", content: "directive-b"})
	store, err := directive.NewPostgresStore(db)
	if err != nil {
		t.Fatalf("store: %v", err)
	}

	// Org B credentials must not resolve Org A's agent directive.
	cross, err := store.Load(context.Background(), orgB.orgID, orgA.agentID)
	if err != nil {
		t.Fatalf("cross load: %v", err)
	}
	if cross.HasContent() {
		t.Fatalf("cross-tenant leak: %+v", cross)
	}

	own, err := store.Load(context.Background(), orgB.orgID, orgB.agentID)
	if err != nil {
		t.Fatalf("own load: %v", err)
	}
	if own.Content != orgB.content {
		t.Fatalf("own content=%q want %q", own.Content, orgB.content)
	}
}

func TestIntegration_CachedResolver_PostgresFallback(t *testing.T) {
	db, _ := openIntegrationDB(t)
	defer db.Close()

	seeded := seedAgentDirective(t, agentDirectiveSeed{db: db, orgName: "Org A", orgSlug: "org-a", content: "Follow org policy."})
	client, resolver := newIntegrationCachedResolver(t, db)
	key := seeded.orgID.String() + ":directive:" + seeded.agentID.String()
	expect := resolveExpect{resolver: resolver, orgID: seeded.orgID, agentID: seeded.agentID, want: seeded.content}

	assertResolveContent(t, expect)
	require.Eventually(t, func() bool { return redisKeyExists(client, key) }, 2*time.Second, 20*time.Millisecond)
	assertResolveContent(t, expect)
	if !redisKeyExists(client, key) {
		t.Fatalf("expected redis key %q", key)
	}
}

func newIntegrationCachedResolver(t *testing.T, db *sql.DB) (*redis.Client, *directive.CachedResolver) {
	t.Helper()
	store, err := directive.NewPostgresStore(db)
	if err != nil {
		t.Fatalf("store: %v", err)
	}
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })
	resolver, err := directive.NewCachedResolver(directive.CachedResolverDeps{
		Client: client, Loader: store, Config: directive.Config{CacheTTL: time.Minute}, Log: mustLogger(t),
	})
	if err != nil {
		t.Fatalf("resolver: %v", err)
	}
	return client, resolver
}

type resolveExpect struct {
	resolver       directive.Resolver
	orgID, agentID uuid.UUID
	want           string
}

func assertResolveContent(t *testing.T, e resolveExpect) {
	t.Helper()
	got, err := e.resolver.Resolve(context.Background(), e.orgID, e.agentID)
	if err != nil {
		t.Fatalf("resolve: %v", err)
	}
	if got.Content != e.want {
		t.Fatalf("content=%q want %q", got.Content, e.want)
	}
}

func redisKeyExists(client *redis.Client, key string) bool {
	return client.Exists(context.Background(), key).Val() == 1
}
