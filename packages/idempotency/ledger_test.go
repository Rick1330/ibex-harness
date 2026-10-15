package idempotency

import (
	"context"
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
	db.Close()
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
	defer db.Close()
	ledger, err := NewPostgresLedger(db, time.Minute)
	if err != nil {
		t.Fatal(err)
	}
	org, agent, id := uuid.New(), uuid.New(), uuid.New()
	hash := HashRequest([]byte("body"))
	mock.ExpectBegin()
	mock.ExpectExec(`SELECT set_config`).WithArgs(org.String()).WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectQuery(`INSERT INTO ibex_core\.idempotency_ledger`).WithArgs(org, agent, "termination-key", hash, "60.000000 seconds").
		WillReturnRows(sqlmock.NewRows([]string{"id", "request_hash", "state", "status_code", "response_payload", "lease_expires_at"}).
			AddRow(id, hash, "claimed", nil, nil, time.Now().UTC().Add(-time.Second)))
	mock.ExpectCommit()
	out, err := ledger.Claim(context.Background(), Principal{OrgID: org, AgentID: agent}, "termination-key", hash)
	if err != nil {
		t.Fatal(err)
	}
	if out.Kind != ClaimOwned || out.Claim.ID != id {
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
	defer db.Close()
	ledger, err := NewPostgresLedger(db, time.Minute)
	if err != nil {
		t.Fatal(err)
	}
	org, agent, id := uuid.New(), uuid.New(), uuid.New()
	hash := HashRequest([]byte("body"))
	claim := ClaimToken{ID: id, Principal: Principal{OrgID: org, AgentID: agent}, Key: "termination-key", RequestHash: hash}
	mock.ExpectExec(`UPDATE ibex_core\.idempotency_ledger`).WithArgs(200, []byte(`{"ok":true}`), id, org, agent, claim.Key, hash).WillReturnResult(sqlmock.NewResult(0, 0))
	if err := ledger.Finalize(context.Background(), claim, 200, []byte(`{"ok":true}`)); !errors.Is(err, ErrLedgerConflict) {
		t.Fatalf("finalize error=%v want conflict for lost claim", err)
	}
	mock.ExpectBegin()
	mock.ExpectExec(`SELECT set_config`).WithArgs(org.String()).WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectQuery(`INSERT INTO ibex_core\.idempotency_ledger`).WithArgs(org, agent, claim.Key, hash, "60.000000 seconds").
		WillReturnRows(sqlmock.NewRows([]string{"id", "request_hash", "state", "status_code", "response_payload", "lease_expires_at"}).
			AddRow(id, hash, "claimed", nil, nil, time.Now().UTC().Add(-time.Second)))
	mock.ExpectCommit()
	out, err := ledger.Claim(context.Background(), claim.Principal, claim.Key, hash)
	if err != nil || out.Kind != ClaimOwned {
		t.Fatalf("reclaim outcome=%+v err=%v", out, err)
	}
	mock.ExpectExec(`UPDATE ibex_core\.idempotency_ledger`).WithArgs(200, []byte(`{"ok":true}`), id, org, agent, claim.Key, hash).WillReturnResult(sqlmock.NewResult(0, 1))
	if err := ledger.Finalize(context.Background(), out.Claim, 200, []byte(`{"ok":true}`)); err != nil {
		t.Fatal(err)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

type ClaimCall struct {
	Principal Principal
	Key, Hash string
}
