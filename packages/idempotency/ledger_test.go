package idempotency

import (
	"context"
	"database/sql"
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/DATA-DOG/go-sqlmock"
	"github.com/google/uuid"
)

func TestHashRequestIsStableAndSized(t *testing.T) {
	a := HashRequest([]byte(`{"status":"completed"}`))
	b := HashRequest([]byte(`{"status":"completed"}`))
	if a != b || len(a) != 64 {
		t.Fatalf("hash=%q stable=%v", a, a == b)
	}
}

func TestPostgresLedgerRejectsUnscopedClaims(t *testing.T) {
	db, _, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = db.Close() })
	ledger, err := NewPostgresLedger(db, 0)
	if err != nil {
		t.Fatal(err)
	}
	cases := []ClaimCall{
		{Principal: Principal{AgentID: uuid.New()}, Key: "k", Hash: "h"},
		{Principal: Principal{OrgID: uuid.New()}, Key: "k", Hash: "h"},
		{Principal: Principal{OrgID: uuid.New(), AgentID: uuid.New()}, Key: "", Hash: "h"},
		{Principal: Principal{OrgID: uuid.New(), AgentID: uuid.New()}, Key: "k", Hash: ""},
	}
	for _, tc := range cases {
		_, err := ledger.Claim(context.Background(), tc.Principal, tc.Key, tc.Hash)
		if !errors.Is(err, ErrInvalidLedgerClaim) {
			t.Fatalf("error=%v want invalid claim", err)
		}
	}
}

func TestPostgresLedgerReclaimsExpiredLease(t *testing.T) {
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = db.Close() })
	ledger, err := NewPostgresLedger(db, time.Minute)
	if err != nil {
		t.Fatal(err)
	}
	org, agent, id := uuid.New(), uuid.New(), uuid.New()
	hash := HashRequest([]byte("body"))
	mock.ExpectBegin()
	mock.ExpectExec(`SELECT set_config`).WithArgs(org.String()).WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectQuery(`INSERT INTO ibex_core\.idempotency_ledger`).WithArgs(org, agent, "termination-key", hash, "60.000000 seconds").
		WillReturnRows(sqlmock.NewRows([]string{"id", "request_hash", "state", "status_code", "response_payload", "lease_expires_at", "version"}))
	mock.ExpectQuery(`SELECT id, request_hash, state`).WithArgs(org, agent, "termination-key").
		WillReturnRows(sqlmock.NewRows([]string{"id", "request_hash", "state", "status_code", "response_payload", "lease_expires_at", "version"}).
			AddRow(id, hash, "claimed", nil, nil, time.Now().UTC().Add(-time.Second), int64(1)))
	mock.ExpectQuery(`UPDATE ibex_core\.idempotency_ledger`).WithArgs("60.000000 seconds", id, org, agent, "termination-key", hash).
		WillReturnRows(sqlmock.NewRows([]string{"id", "request_hash", "state", "status_code", "response_payload", "lease_expires_at", "version"}).
			AddRow(id, hash, "claimed", nil, nil, time.Now().UTC().Add(time.Minute), int64(2)))
	mock.ExpectCommit()
	out, err := ledger.Claim(context.Background(), Principal{OrgID: org, AgentID: agent}, "termination-key", hash)
	if err != nil {
		t.Fatal(err)
	}
	if out.Kind != ClaimOwned || out.Claim.ID != id || out.Claim.Version != 2 {
		t.Fatalf("outcome=%+v want reclaimed ownership", out)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestPostgresLedgerFinalizeFailureCanBeRecoveredByReclaim(t *testing.T) {
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = db.Close() })
	ledger, err := NewPostgresLedger(db, time.Minute)
	if err != nil {
		t.Fatal(err)
	}
	org, agent, id := uuid.New(), uuid.New(), uuid.New()
	hash := HashRequest([]byte("body"))
	claim := ClaimToken{ID: id, Principal: Principal{OrgID: org, AgentID: agent}, Key: "termination-key", RequestHash: hash, Version: 1}
	mock.ExpectBegin()
	mock.ExpectExec(`SELECT set_config`).WithArgs(org.String()).WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectExec(`UPDATE ibex_core\.idempotency_ledger`).WithArgs(200, []byte(`{"ok":true}`), id, org, agent, claim.Key, hash, int64(1)).WillReturnResult(sqlmock.NewResult(0, 0))
	if err := ledger.Finalize(context.Background(), claim, 200, []byte(`{"ok":true}`)); !errors.Is(err, ErrLedgerConflict) {
		t.Fatalf("finalize error=%v want conflict for lost claim", err)
	}
	mock.ExpectBegin()
	mock.ExpectExec(`SELECT set_config`).WithArgs(org.String()).WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectQuery(`INSERT INTO ibex_core\.idempotency_ledger`).WithArgs(org, agent, claim.Key, hash, "60.000000 seconds").
		WillReturnRows(sqlmock.NewRows([]string{"id", "request_hash", "state", "status_code", "response_payload", "lease_expires_at", "version"}))
	mock.ExpectQuery(`SELECT id, request_hash, state`).WithArgs(org, agent, claim.Key).
		WillReturnRows(sqlmock.NewRows([]string{"id", "request_hash", "state", "status_code", "response_payload", "lease_expires_at", "version"}).
			AddRow(id, hash, "claimed", nil, nil, time.Now().UTC().Add(-time.Second), int64(1)))
	mock.ExpectQuery(`UPDATE ibex_core\.idempotency_ledger`).WithArgs("60.000000 seconds", id, org, agent, claim.Key, hash).
		WillReturnRows(sqlmock.NewRows([]string{"id", "request_hash", "state", "status_code", "response_payload", "lease_expires_at", "version"}).
			AddRow(id, hash, "claimed", nil, nil, time.Now().UTC().Add(time.Minute), int64(2)))
	mock.ExpectCommit()
	out, err := ledger.Claim(context.Background(), claim.Principal, claim.Key, hash)
	if err != nil || out.Kind != ClaimOwned {
		t.Fatalf("reclaim outcome=%+v err=%v", out, err)
	}
	mock.ExpectBegin()
	mock.ExpectExec(`SELECT set_config`).WithArgs(org.String()).WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectExec(`UPDATE ibex_core\.idempotency_ledger`).WithArgs(200, []byte(`{"ok":true}`), id, org, agent, claim.Key, hash, int64(2)).WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectCommit()
	if err := ledger.Finalize(context.Background(), out.Claim, 200, []byte(`{"ok":true}`)); err != nil {
		t.Fatal(err)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestPostgresLedgerCrossTenantIsolation(t *testing.T) {
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = db.Close() })
	ledger, err := NewPostgresLedger(db, time.Minute)
	if err != nil {
		t.Fatal(err)
	}
	orgA, orgB, agent := uuid.New(), uuid.New(), uuid.New()
	id, hash := uuid.New(), HashRequest([]byte("tenant-a"))
	mock.ExpectBegin()
	mock.ExpectExec(`SELECT set_config`).WithArgs(orgA.String()).WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectQuery(`INSERT INTO ibex_core\.idempotency_ledger`).WithArgs(orgA, agent, "shared-key", hash, "60.000000 seconds").
		WillReturnRows(sqlmock.NewRows([]string{"id", "request_hash", "state", "status_code", "response_payload", "lease_expires_at", "version"}).
			AddRow(id, hash, "claimed", nil, nil, time.Now().UTC().Add(time.Minute), int64(1)))
	mock.ExpectCommit()
	if out, err := ledger.Claim(context.Background(), Principal{OrgID: orgA, AgentID: agent}, "shared-key", hash); err != nil || out.Kind != ClaimOwned {
		t.Fatalf("tenant A claim=%+v err=%v", out, err)
	}

	otherHash := HashRequest([]byte("tenant-b"))
	mock.ExpectBegin()
	mock.ExpectExec(`SELECT set_config`).WithArgs(orgB.String()).WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectQuery(`INSERT INTO ibex_core\.idempotency_ledger`).WithArgs(orgB, agent, "shared-key", otherHash, "60.000000 seconds").
		WillReturnRows(sqlmock.NewRows([]string{"id", "request_hash", "state", "status_code", "response_payload", "lease_expires_at", "version"}))
	mock.ExpectQuery(`SELECT id, request_hash, state`).WithArgs(orgB, agent, "shared-key").WillReturnError(sql.ErrNoRows)
	if _, err := ledger.Claim(context.Background(), Principal{OrgID: orgB, AgentID: agent}, "shared-key", otherHash); !errors.Is(err, sql.ErrNoRows) {
		t.Fatalf("cross-tenant claim error=%v want no visible row", err)
	}

	claim := ClaimToken{ID: id, Principal: Principal{OrgID: orgB, AgentID: agent}, Key: "shared-key", RequestHash: hash, Version: 1}
	mock.ExpectBegin()
	mock.ExpectExec(`SELECT set_config`).WithArgs(orgB.String()).WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectExec(`UPDATE ibex_core\.idempotency_ledger`).WithArgs(200, []byte(`{"ok":true}`), id, orgB, agent, claim.Key, hash, int64(1)).WillReturnResult(sqlmock.NewResult(0, 0))
	if err := ledger.Finalize(context.Background(), claim, 200, []byte(`{"ok":true}`)); !errors.Is(err, ErrLedgerConflict) {
		t.Fatalf("cross-tenant finalize error=%v want conflict", err)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestPostgresLedgerConstructorAndClaimFailures(t *testing.T) {
	assertLedgerConstructorValidation(t)
	assertClaimBeginAndScopeFailures(t)
}

func assertLedgerConstructorValidation(t *testing.T) {
	if _, err := NewPostgresLedger(nil, time.Minute); err == nil {
		t.Fatal("nil database must fail")
	}
	if ledger, err := NewOptionalPostgresLedger(nil, time.Minute); ledger != nil || err != nil {
		t.Fatalf("optional nil database ledger=%v err=%v", ledger, err)
	}
	db, _, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = db.Close() })
	ledger, err := NewPostgresLedger(db, 0)
	if err != nil || ledger.lease != 2*time.Minute {
		t.Fatalf("default lease=%v err=%v", ledger.lease, err)
	}
	if optional, err := NewOptionalPostgresLedger(db, time.Minute); err != nil || optional == nil {
		t.Fatalf("optional database ledger=%v err=%v", optional, err)
	}
}

func assertClaimBeginAndScopeFailures(t *testing.T) {
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = db.Close() })
	ledger, err := NewPostgresLedger(db, 0)
	if err != nil {
		t.Fatal(err)
	}
	org, agent := uuid.New(), uuid.New()
	mock.ExpectBegin().WillReturnError(errors.New("begin failed"))
	if _, err := ledger.Claim(context.Background(), Principal{OrgID: org, AgentID: agent}, "k", HashRequest([]byte("b"))); err == nil || !strings.Contains(err.Error(), "begin failed") {
		t.Fatalf("claim begin error=%v", err)
	}
	mock.ExpectBegin()
	mock.ExpectExec(`SELECT set_config`).WithArgs(org.String()).WillReturnError(errors.New("scope failed"))
	if _, err := ledger.Claim(context.Background(), Principal{OrgID: org, AgentID: agent}, "k", HashRequest([]byte("b"))); err == nil || !strings.Contains(err.Error(), "scope failed") {
		t.Fatalf("claim scope error=%v", err)
	}
	mock.ExpectBegin()
	mock.ExpectExec(`SELECT set_config`).WithArgs(org.String()).WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectQuery(`INSERT INTO ibex_core\.idempotency_ledger`).WillReturnError(errors.New("insert failed"))
	if _, err := ledger.Claim(context.Background(), Principal{OrgID: org, AgentID: agent}, "k", HashRequest([]byte("b"))); err == nil || !strings.Contains(err.Error(), "insert failed") {
		t.Fatalf("claim insert error=%v", err)
	}
	mock.ExpectBegin()
	mock.ExpectExec(`SELECT set_config`).WithArgs(org.String()).WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectQuery(`INSERT INTO ibex_core\.idempotency_ledger`).WithArgs(org, agent, "k", HashRequest([]byte("b")), "120.000000 seconds").WillReturnRows(sqlmock.NewRows([]string{"id", "request_hash", "state", "status_code", "response_payload", "lease_expires_at", "version"}).AddRow(uuid.New(), HashRequest([]byte("b")), "claimed", nil, nil, time.Now().Add(time.Minute), 1))
	mock.ExpectCommit().WillReturnError(errors.New("commit failed"))
	if _, err := ledger.Claim(context.Background(), Principal{OrgID: org, AgentID: agent}, "k", HashRequest([]byte("b"))); err == nil || !strings.Contains(err.Error(), "commit failed") {
		t.Fatalf("claim commit error=%v", err)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestPostgresLedgerClaimStates(t *testing.T) {
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = db.Close() })
	ledger, _ := NewPostgresLedger(db, time.Minute)
	org, agent, id := uuid.New(), uuid.New(), uuid.New()
	key := "state-key"
	row := func(hash, state string, status any, response any, expires any, version int64) *sqlmock.Rows {
		return sqlmock.NewRows([]string{"id", "request_hash", "state", "status_code", "response_payload", "lease_expires_at", "version"}).AddRow(id, hash, state, status, response, expires, version)
	}
	claim := func(hash string, rows *sqlmock.Rows, commit bool) (ClaimOutcome, error) {
		mock.ExpectBegin()
		mock.ExpectExec(`SELECT set_config`).WithArgs(org.String()).WillReturnResult(sqlmock.NewResult(0, 1))
		mock.ExpectQuery(`INSERT INTO ibex_core\.idempotency_ledger`).WithArgs(org, agent, key, hash, "60.000000 seconds").WillReturnRows(sqlmock.NewRows([]string{"id", "request_hash", "state", "status_code", "response_payload", "lease_expires_at", "version"}))
		mock.ExpectQuery(`SELECT id, request_hash, state`).WithArgs(org, agent, key).WillReturnRows(rows)
		if commit {
			mock.ExpectCommit()
		}
		out, err := ledger.Claim(context.Background(), Principal{OrgID: org, AgentID: agent}, key, hash)
		return out, err
	}
	hash := HashRequest([]byte("same"))
	out, err := claim(HashRequest([]byte("other")), row(hash, "claimed", nil, nil, time.Now().Add(time.Minute), 1), true)
	if err != nil || out.Kind != ClaimConflict {
		t.Fatalf("conflict outcome=%+v err=%v", out, err)
	}
	out, err = claim(hash, row(hash, "finalized", 200, []byte(`{"ok":true}`), nil, 1), true)
	if err != nil || out.Kind != ClaimReplay || out.Status != 200 {
		t.Fatalf("replay outcome=%+v err=%v", out, err)
	}
	out, err = claim(hash, row(hash, "claimed", nil, nil, time.Now().Add(time.Minute), 1), true)
	if err != nil || out.Kind != ClaimInProgress {
		t.Fatalf("in-progress outcome=%+v err=%v", out, err)
	}
	out, err = claim(hash, row(hash, "failed_terminal", nil, nil, time.Now().Add(time.Minute), 1), false)
	if err == nil || out.Kind != "" {
		t.Fatalf("unsupported state outcome=%+v err=%v", out, err)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
	assertExpiredLeaseReclaimProbes(t, ledger, mock, org, agent, key)
}

func assertExpiredLeaseReclaimProbes(t *testing.T, ledger *PostgresLedger, mock sqlmock.Sqlmock, org, agent uuid.UUID, key string) {
	hash := HashRequest([]byte("same"))
	row := func(state string, expires any) *sqlmock.Rows {
		return sqlmock.NewRows([]string{"id", "request_hash", "state", "status_code", "response_payload", "lease_expires_at", "version"}).AddRow(uuid.New(), hash, state, nil, nil, expires, 1)
	}
	mock.ExpectBegin()
	mock.ExpectExec(`SELECT set_config`).WithArgs(org.String()).WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectQuery(`INSERT INTO ibex_core\.idempotency_ledger`).WithArgs(org, agent, key, hash, "60.000000 seconds").WillReturnRows(sqlmock.NewRows([]string{"id", "request_hash", "state", "status_code", "response_payload", "lease_expires_at", "version"}))
	mock.ExpectQuery(`SELECT id, request_hash, state`).WithArgs(org, agent, key).WillReturnRows(row("claimed", time.Now().Add(-time.Minute)))
	mock.ExpectQuery(`UPDATE ibex_core\.idempotency_ledger`).WillReturnError(errors.New("reclaim failed"))
	if _, err := ledger.Claim(context.Background(), Principal{OrgID: org, AgentID: agent}, key, hash); err == nil || !strings.Contains(err.Error(), "reclaim failed") {
		t.Fatalf("reclaim error=%v", err)
	}
	mock.ExpectBegin()
	mock.ExpectExec(`SELECT set_config`).WithArgs(org.String()).WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectQuery(`INSERT INTO ibex_core\.idempotency_ledger`).WithArgs(org, agent, key, hash, "60.000000 seconds").WillReturnRows(sqlmock.NewRows([]string{"id", "request_hash", "state", "status_code", "response_payload", "lease_expires_at", "version"}))
	mock.ExpectQuery(`SELECT id, request_hash, state`).WithArgs(org, agent, key).WillReturnRows(row("claimed", time.Now().Add(-time.Minute)))
	mock.ExpectQuery(`UPDATE ibex_core\.idempotency_ledger`).WillReturnError(sql.ErrNoRows)
	mock.ExpectCommit()
	out, err := ledger.Claim(context.Background(), Principal{OrgID: org, AgentID: agent}, key, hash)
	if err != nil || out.Kind != ClaimInProgress || out.RetryAfter <= 0 {
		t.Fatalf("clock-race outcome=%+v err=%v", out, err)
	}
}

func TestPostgresLedgerFinalizeFailures(t *testing.T) {
	claim := ClaimToken{ID: uuid.New(), Principal: Principal{OrgID: uuid.New(), AgentID: uuid.New()}, Key: "k", RequestHash: HashRequest([]byte("b")), Version: 1}
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = db.Close() })
	ledger, _ := NewPostgresLedger(db, time.Minute)
	if err := ledger.Finalize(context.Background(), ClaimToken{}, 200, nil); !errors.Is(err, ErrInvalidLedgerClaim) {
		t.Fatalf("invalid finalize error=%v", err)
	}
	mock.ExpectBegin().WillReturnError(errors.New("begin failed"))
	if err := ledger.Finalize(context.Background(), claim, 200, nil); err == nil || !strings.Contains(err.Error(), "begin failed") {
		t.Fatalf("finalize begin error=%v", err)
	}
	mock.ExpectBegin()
	mock.ExpectExec(`SELECT set_config`).WithArgs(claim.Principal.OrgID.String()).WillReturnError(errors.New("scope failed"))
	if err := ledger.Finalize(context.Background(), claim, 200, nil); err == nil || !strings.Contains(err.Error(), "scope failed") {
		t.Fatalf("finalize scope error=%v", err)
	}
	mock.ExpectBegin()
	mock.ExpectExec(`SELECT set_config`).WithArgs(claim.Principal.OrgID.String()).WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectExec(`UPDATE ibex_core\.idempotency_ledger`).WillReturnError(errors.New("update failed"))
	if err := ledger.Finalize(context.Background(), claim, 200, nil); err == nil || !strings.Contains(err.Error(), "update failed") {
		t.Fatalf("finalize update error=%v", err)
	}
	mock.ExpectBegin()
	mock.ExpectExec(`SELECT set_config`).WithArgs(claim.Principal.OrgID.String()).WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectExec(`UPDATE ibex_core\.idempotency_ledger`).WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectCommit().WillReturnError(errors.New("commit failed"))
	if err := ledger.Finalize(context.Background(), claim, 200, nil); err == nil || !strings.Contains(err.Error(), "commit failed") {
		t.Fatalf("finalize commit error=%v", err)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

type ClaimCall struct {
	Principal Principal
	Key, Hash string
}
