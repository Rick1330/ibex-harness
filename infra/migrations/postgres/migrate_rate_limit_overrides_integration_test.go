//go:build integration

package postgres

import (
	"context"
	"database/sql"
	"errors"
	"testing"

	"github.com/lib/pq"
)

func TestRateLimitOverrides_orgLevelPartialUnique(t *testing.T) {
	dsn := testDSN()
	db := openTestDB(t)
	defer db.Close()
	resetSchema(t, db)
	if err := Up(dsn); err != nil {
		t.Fatalf("up: %v", err)
	}

	ctx := context.Background()
	var orgID, agentID string
	err := withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		var e error
		orgID, e = insertOrg(ctx, tx, "RL Org", "rl-org")
		if e != nil {
			return e
		}
		return insertUserAndAgent(ctx, tx, orgID, userAgentSeed{
			email: "rl@example.com", name: "RL User", agent: "RL Agent", slug: "rl-agent",
		})
	})
	if err != nil {
		t.Fatalf("seed: %v", err)
	}
	err = withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		return tx.QueryRowContext(ctx, `
			SELECT id::text FROM ibex_core.agents WHERE org_id = $1::uuid LIMIT 1`, orgID).Scan(&agentID)
	})
	if err != nil {
		t.Fatalf("agent id: %v", err)
	}

	insertOrgLevel := `
		INSERT INTO ibex_core.rate_limit_overrides (org_id, agent_id, requests_per_minute)
		VALUES ($1::uuid, NULL, 120)`
	err = withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		_, e := tx.ExecContext(ctx, insertOrgLevel, orgID)
		return e
	})
	if err != nil {
		t.Fatalf("first org-level insert: %v", err)
	}
	err = withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		_, e := tx.ExecContext(ctx, insertOrgLevel, orgID)
		return e
	})
	assertUniqueViolation(t, err, "duplicate org-level override")

	insertAgent := `
		INSERT INTO ibex_core.rate_limit_overrides (org_id, agent_id, requests_per_minute)
		VALUES ($1::uuid, $2::uuid, 30)`
	err = withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		_, e := tx.ExecContext(ctx, insertAgent, orgID, agentID)
		return e
	})
	if err != nil {
		t.Fatalf("first agent override: %v", err)
	}
	err = withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		_, e := tx.ExecContext(ctx, insertAgent, orgID, agentID)
		return e
	})
	assertUniqueViolation(t, err, "duplicate agent override")
}

func assertUniqueViolation(t *testing.T, err error, label string) {
	t.Helper()
	if err == nil {
		t.Fatalf("%s: expected unique violation", label)
	}
	var pqErr *pq.Error
	if !errors.As(err, &pqErr) || pqErr.Code != "23505" {
		t.Fatalf("%s: want unique_violation, got %v", label, err)
	}
}
