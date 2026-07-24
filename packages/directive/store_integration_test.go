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

	_ "github.com/lib/pq"
)

const defaultTestDSN = "postgres://ibex:ibex@localhost:5433/ibex_test?sslmode=disable"

func integrationDSN() string {
	if dsn := os.Getenv("POSTGRES_TEST_DSN"); dsn != "" {
		return dsn
	}
	return defaultTestDSN
}

func openIntegrationDB(t *testing.T) (*sql.DB, string) {
	t.Helper()
	dsn := integrationDSN()
	if os.Getenv("POSTGRES_TEST_DSN") != "" {
		dsn = os.Getenv("POSTGRES_TEST_DSN")
	}
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

func seedAgentDirective(t *testing.T, db *sql.DB, content string) seededAgentDirective {
	t.Helper()
	ctx := context.Background()
	var orgID, userID, agentID, directiveID, versionID string
	err := withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		if err := tx.QueryRowContext(ctx, `
			INSERT INTO ibex_core.organizations (name, slug)
			VALUES ('Org A', 'org-a') RETURNING id::text`).Scan(&orgID); err != nil {
			return err
		}
		if err := tx.QueryRowContext(ctx, `
			INSERT INTO ibex_core.users (org_id, email, name)
			VALUES ($1::uuid, 'user-a@example.com', 'User A') RETURNING id::text`, orgID).Scan(&userID); err != nil {
			return err
		}
		if err := tx.QueryRowContext(ctx, `
			INSERT INTO ibex_core.agents (org_id, created_by, name, slug)
			VALUES ($1::uuid, $2::uuid, 'Agent A', 'agent-a') RETURNING id::text`, orgID, userID).Scan(&agentID); err != nil {
			return err
		}
		if err := tx.QueryRowContext(ctx, `
			INSERT INTO ibex_core.directives (org_id, agent_id)
			VALUES ($1::uuid, $2::uuid) RETURNING id::text`, orgID, agentID).Scan(&directiveID); err != nil {
			return err
		}
		if err := tx.QueryRowContext(ctx, `
			INSERT INTO ibex_core.directive_versions
				(directive_id, org_id, version_num, content, content_hash)
			VALUES ($1::uuid, $2::uuid, 1, $3, $4) RETURNING id::text`,
			directiveID, orgID, content, "hash-"+content).Scan(&versionID); err != nil {
			return err
		}
		_, err := tx.ExecContext(ctx, `
			UPDATE ibex_core.directives SET active_version_id = $1::uuid WHERE id = $2::uuid`,
			versionID, directiveID)
		return err
	})
	if err != nil {
		t.Fatalf("seed: %v", err)
	}
	return seededAgentDirective{
		orgID:   uuid.MustParse(orgID),
		agentID: uuid.MustParse(agentID),
		content: content,
	}
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

	seeded := seedAgentDirective(t, db, "Be concise and safe.")
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

func TestIntegration_CachedResolver_PostgresFallback(t *testing.T) {
	db, _ := openIntegrationDB(t)
	defer db.Close()

	seeded := seedAgentDirective(t, db, "Follow org policy.")
	store, err := directive.NewPostgresStore(db)
	if err != nil {
		t.Fatalf("store: %v", err)
	}
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })
	log := mustLogger(t)

	resolver, err := directive.NewCachedResolver(client, store, directive.Config{CacheTTL: time.Minute}, log, nil)
	if err != nil {
		t.Fatalf("resolver: %v", err)
	}

	first, err := resolver.Resolve(context.Background(), seeded.orgID, seeded.agentID)
	if err != nil {
		t.Fatalf("first resolve: %v", err)
	}
	if first.Content != seeded.content {
		t.Fatalf("first content=%q", first.Content)
	}

	second, err := resolver.Resolve(context.Background(), seeded.orgID, seeded.agentID)
	if err != nil {
		t.Fatalf("second resolve: %v", err)
	}
	if second.Content != seeded.content {
		t.Fatalf("cache hit content=%q", second.Content)
	}

	key := seeded.orgID.String() + ":directive:" + seeded.agentID.String()
	if !mr.Exists(key) {
		t.Fatalf("expected redis key %q", key)
	}
}
