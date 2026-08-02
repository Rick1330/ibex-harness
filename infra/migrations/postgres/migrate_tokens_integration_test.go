//go:build integration

package postgres

import (
	"context"
	"database/sql"
	"errors"
	"testing"

	"github.com/google/uuid"
	"github.com/lib/pq"
)

const insertTokenWithAgentSQL = `
	INSERT INTO ibex_core.tokens
		(org_id, type, hash, prefix, name, permissions, is_revoked, agent_id)
	VALUES
		($1::uuid, 'pat', $2, $3, $4, 0, false, $5::uuid)`

const insertTokenWithUserSQL = `
	INSERT INTO ibex_core.tokens
		(org_id, type, hash, prefix, name, permissions, is_revoked, user_id)
	VALUES
		($1::uuid, 'pat', $2, $3, $4, 0, false, $5::uuid)`

type userLookup struct {
	db           *sql.DB
	orgID, email string
}

type tokenSubjectInsert struct {
	db               *sql.DB
	label            string
	orgID, subjectID string
	sqlText          string
}

func TestTokens_CompositeFKOwnership(t *testing.T) {
	dsn := testDSN()
	db := openTestDB(t)
	defer db.Close()
	resetSchema(t, db)
	if err := Up(dsn); err != nil {
		t.Fatalf("up: %v", err)
	}

	ctx := context.Background()
	orgA, orgB := seedTwoOrgsWithAgents(t, ctx, db)
	agentA := lookupAgentID(t, ctx, agentLookup{db: db, orgID: orgA, slug: "agent-a"})
	agentB := lookupAgentID(t, ctx, agentLookup{db: db, orgID: orgB, slug: "agent-b"})
	userA := lookupUserID(t, ctx, userLookup{db: db, orgID: orgA, email: "user-a@example.com"})
	userB := lookupUserID(t, ctx, userLookup{db: db, orgID: orgB, email: "user-b@example.com"})

	assertTokenFKDenied(t, ctx, tokenSubjectInsert{
		db: db, label: "cross-org agent_id", orgID: orgA, subjectID: agentB, sqlText: insertTokenWithAgentSQL,
	})
	assertTokenFKDenied(t, ctx, tokenSubjectInsert{
		db: db, label: "cross-org user_id", orgID: orgA, subjectID: userB, sqlText: insertTokenWithUserSQL,
	})
	assertTokenInsertOK(t, ctx, tokenSubjectInsert{
		db: db, label: "same-org agent_id", orgID: orgA, subjectID: agentA, sqlText: insertTokenWithAgentSQL,
	})
	assertTokenInsertOK(t, ctx, tokenSubjectInsert{
		db: db, label: "same-org user_id", orgID: orgA, subjectID: userA, sqlText: insertTokenWithUserSQL,
	})
}

func assertTokenFKDenied(t *testing.T, ctx context.Context, in tokenSubjectInsert) {
	t.Helper()
	err := withServiceAccount(ctx, in.db, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(ctx, in.sqlText,
			in.orgID, uniqueTokenHash(), uniqueTokenPrefix(), "tok-"+in.label, in.subjectID)
		return err
	})
	if err == nil {
		t.Fatalf("expected %s FK to fail", in.label)
	}
	assertFKViolation(t, err)
}

func assertTokenInsertOK(t *testing.T, ctx context.Context, in tokenSubjectInsert) {
	t.Helper()
	err := withServiceAccount(ctx, in.db, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(ctx, in.sqlText,
			in.orgID, uniqueTokenHash(), uniqueTokenPrefix(), "tok-"+in.label, in.subjectID)
		return err
	})
	if err != nil {
		t.Fatalf("expected %s insert to succeed: %v", in.label, err)
	}
}

func assertFKViolation(t *testing.T, err error) {
	t.Helper()
	var pqErr *pq.Error
	if !errors.As(err, &pqErr) {
		t.Fatalf("expected *pq.Error, got %T: %v", err, err)
	}
	if pqErr.Code != "23503" {
		t.Fatalf("expected SQLSTATE 23503, got %s", pqErr.Code)
	}
}

func lookupUserID(t *testing.T, ctx context.Context, q userLookup) string {
	t.Helper()
	var userID string
	err := withServiceAccount(ctx, q.db, func(tx *sql.Tx) error {
		return tx.QueryRowContext(ctx, `
			SELECT id::text FROM ibex_core.users
			WHERE org_id = $1::uuid AND email = $2`, q.orgID, q.email).Scan(&userID)
	})
	if err != nil {
		t.Fatalf("lookup user: %v", err)
	}
	return userID
}

func uniqueTokenHash() string {
	return "hash_" + uuid.New().String()
}

func uniqueTokenPrefix() string {
	return "ibex_pat_" + uuid.New().String()[:8]
}
