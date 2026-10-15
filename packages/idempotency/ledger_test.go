package idempotency

import (
	"context"
	"database/sql"
	"errors"
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

type ClaimCall struct {
	Principal Principal
	Key, Hash string
}
