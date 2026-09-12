//go:build integration

package modelpolicy_test

import (
	"context"
	"database/sql"
	"os"
	"testing"
	"time"

	migratepg "github.com/Rick1330/ibex-harness/infra/migrations/postgres"
	"github.com/Rick1330/ibex-harness/packages/modelpolicy"
	"github.com/google/uuid"

	_ "github.com/lib/pq" // database/sql Postgres driver for integration DSN
)

const defaultTestDSN = "postgres://ibex:ibex@localhost:5433/ibex_test?sslmode=disable"

type policySeed struct {
	pattern  string
	allowed  bool
	priority int
}

func integrationDSN() string {
	if dsn := os.Getenv("POSTGRES_TEST_DSN"); dsn != "" {
		return dsn
	}
	return defaultTestDSN
}

func openIntegrationDB(t *testing.T) *sql.DB {
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
	resetSchema(t, db)
	if err := migratepg.Up(dsn); err != nil {
		t.Fatalf("migrate up: %v", err)
	}
	return db
}

func resetSchema(t *testing.T, db *sql.DB) {
	t.Helper()
	ctx := context.Background()
	_, _ = db.ExecContext(ctx, `DROP SCHEMA IF EXISTS ibex_core CASCADE`)
	_, _ = db.ExecContext(ctx, `DROP TABLE IF EXISTS schema_migrations`)
	_, _ = db.ExecContext(ctx, `DROP ROLE IF EXISTS ibex_app`)
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

func seedOrg(t *testing.T, db *sql.DB, slug string) uuid.UUID {
	t.Helper()
	var orgID string
	err := withServiceAccount(context.Background(), db, func(tx *sql.Tx) error {
		return tx.QueryRowContext(context.Background(),
			`INSERT INTO ibex_core.organizations (name, slug) VALUES ($1, $2) RETURNING id::text`,
			slug+" Org", slug,
		).Scan(&orgID)
	})
	if err != nil {
		t.Fatalf("seed org: %v", err)
	}
	return uuid.MustParse(orgID)
}

func insertPolicy(t *testing.T, db *sql.DB, orgID uuid.UUID, seed policySeed) {
	t.Helper()
	err := withServiceAccount(context.Background(), db, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(context.Background(), `
			INSERT INTO ibex_core.org_model_policies (org_id, model_pattern, allowed, priority)
			VALUES ($1::uuid, $2, $3, $4)`, orgID, seed.pattern, seed.allowed, seed.priority)
		return err
	})
	if err != nil {
		t.Fatalf("insert policy: %v", err)
	}
}

func mustStore(t *testing.T, db *sql.DB) *modelpolicy.Store {
	t.Helper()
	store, err := modelpolicy.NewStore(db)
	if err != nil {
		t.Fatal(err)
	}
	return store
}

type decisionWant struct {
	model       string
	wantMatched bool
	wantAllowed bool
}

func assertDecision(t *testing.T, policies []modelpolicy.Policy, want decisionWant) {
	t.Helper()
	dec, err := modelpolicy.EvaluatePolicies(policies, want.model)
	if err != nil {
		t.Fatal(err)
	}
	if dec.Matched != want.wantMatched || dec.Allowed != want.wantAllowed {
		t.Fatalf("model=%s got matched=%v allowed=%v want matched=%v allowed=%v",
			want.model, dec.Matched, dec.Allowed, want.wantMatched, want.wantAllowed)
	}
}

func TestRouting_OrgPolicy_StoreEvaluate(t *testing.T) {
	db := openIntegrationDB(t)
	defer db.Close()

	org := seedOrg(t, db, "mp-routing-a")
	insertPolicy(t, db, org, policySeed{pattern: "claude-sonnet-4-5", allowed: false, priority: 1})
	insertPolicy(t, db, org, policySeed{pattern: "claude-*", allowed: true, priority: 10})

	policies, err := mustStore(t, db).LoadOrg(context.Background(), org)
	if err != nil {
		t.Fatal(err)
	}
	if len(policies) != 2 {
		t.Fatalf("len=%d want 2", len(policies))
	}
	assertDecision(t, policies, decisionWant{model: "claude-sonnet-4-5", wantMatched: true, wantAllowed: false})
	assertDecision(t, policies, decisionWant{model: "claude-opus-4", wantMatched: true, wantAllowed: true})
	assertDecision(t, policies, decisionWant{model: "gpt-4o", wantMatched: false, wantAllowed: true})
}

func TestRouting_OrgPolicy_CrossTenantIsolation(t *testing.T) {
	db := openIntegrationDB(t)
	defer db.Close()

	orgA := seedOrg(t, db, "mp-iso-a")
	orgB := seedOrg(t, db, "mp-iso-b")
	insertPolicy(t, db, orgA, policySeed{pattern: "claude-*", allowed: false, priority: 1})

	store := mustStore(t, db)
	polsA, err := store.LoadOrg(context.Background(), orgA)
	if err != nil {
		t.Fatal(err)
	}
	if len(polsA) != 1 {
		t.Fatalf("orgA len=%d", len(polsA))
	}
	polsB, err := store.LoadOrg(context.Background(), orgB)
	if err != nil {
		t.Fatal(err)
	}
	if len(polsB) != 0 {
		t.Fatalf("orgB must not see orgA policies: %d", len(polsB))
	}
}

func TestAgentStore_LoadDefaults(t *testing.T) {
	db := openIntegrationDB(t)
	defer db.Close()

	org := seedOrg(t, db, "mp-agent-defaults")
	agentID := seedAgentWithDefaults(t, db, org, "gpt-4o", "openai")

	store, err := modelpolicy.NewAgentStore(db)
	if err != nil {
		t.Fatal(err)
	}
	got, err := store.Load(context.Background(), org, agentID)
	if err != nil {
		t.Fatal(err)
	}
	if got.DefaultModel != "gpt-4o" || got.DefaultProvider != "openai" {
		t.Fatalf("got=%+v", got)
	}

	missing, err := store.Load(context.Background(), org, uuid.New())
	if err != nil {
		t.Fatal(err)
	}
	if missing.DefaultModel != "" || missing.DefaultProvider != "" {
		t.Fatalf("missing agent must be empty: %+v", missing)
	}
}

func seedAgentWithDefaults(t *testing.T, db *sql.DB, orgID uuid.UUID, model, provider string) uuid.UUID {
	t.Helper()
	var agentID string
	err := withServiceAccount(context.Background(), db, func(tx *sql.Tx) error {
		return tx.QueryRowContext(context.Background(), `
			INSERT INTO ibex_core.agents (org_id, name, slug, default_model, default_provider)
			VALUES ($1::uuid, 'Agent', 'agent-defaults', $2, $3)
			RETURNING id::text`, orgID, model, provider).Scan(&agentID)
	})
	if err != nil {
		t.Fatalf("seed agent: %v", err)
	}
	return uuid.MustParse(agentID)
}
