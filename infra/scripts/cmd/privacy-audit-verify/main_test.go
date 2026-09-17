package main

import (
	"context"
	"database/sql"
	"encoding/json"
	"testing"
	"time"

	"github.com/DATA-DOG/go-sqlmock"
	"github.com/Rick1330/ibex-harness/packages/privacyaudit"
	"github.com/google/uuid"
	"github.com/lib/pq"
)

func newMockDB(t *testing.T) (*sql.DB, sqlmock.Sqlmock) {
	t.Helper()
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = db.Close() })
	return db, mock
}

func entryColumns() []string {
	return []string{
		"org_id", "seq", "prev_hash", "row_hash",
		"actor_user_id", "action", "purpose", "policy_result",
		"object_type", "object_id", "fields",
		"approval_ref", "before_hash", "after_hash",
		"correlation_id", "request_id", "payload", "created_at",
	}
}

func expectSetOrgTx(mock sqlmock.Sqlmock, org uuid.UUID) {
	mock.ExpectBegin()
	mock.ExpectExec(`SELECT set_config`).WithArgs(org.String()).
		WillReturnResult(sqlmock.NewResult(0, 1))
}

func expectEmptyLedger(mock sqlmock.Sqlmock, org uuid.UUID) {
	expectSetOrgTx(mock, org)
	mock.ExpectQuery("SELECT org_id, seq").WithArgs(org).
		WillReturnRows(sqlmock.NewRows(entryColumns()))
	mock.ExpectCommit()
}

func TestRun_MissingDSN(t *testing.T) {
	t.Setenv("POSTGRES_DSN", "")
	if code := run([]string{}); code != 2 {
		t.Fatalf("code=%d", code)
	}
}

func TestRun_BadFlag(t *testing.T) {
	if code := run([]string{"-unknown"}); code != 2 {
		t.Fatalf("code=%d", code)
	}
}

func TestVerifyDB_EmptyOK(t *testing.T) {
	db, mock := newMockDB(t)
	mock.ExpectQuery("privacy_audit_list_orgs").
		WillReturnRows(sqlmock.NewRows([]string{"org_id"}))
	if code := verifyDB(context.Background(), db, ""); code != 0 {
		t.Fatalf("code=%d", code)
	}
}

func TestVerifyDB_ListError(t *testing.T) {
	db, mock := newMockDB(t)
	mock.ExpectQuery("privacy_audit_list_orgs").WillReturnError(context.Canceled)
	if code := verifyDB(context.Background(), db, ""); code != 2 {
		t.Fatalf("code=%d", code)
	}
}

func TestVerifyDB_ChainFail(t *testing.T) {
	db, mock := newMockDB(t)
	org := uuid.New()
	ts := time.Now().UTC()
	expectSetOrgTx(mock, org)
	mock.ExpectQuery("SELECT org_id, seq").WithArgs(org).WillReturnRows(sqlmock.NewRows(entryColumns()).AddRow(
		org, int64(1), privacyaudit.GenesisPrevHash, "bad",
		nil, "a", "", "",
		"", "", pq.StringArray{},
		"", "", "",
		"", "", []byte(`{}`), ts,
	))
	mock.ExpectRollback()
	if code := verifyDB(context.Background(), db, org.String()); code != 1 {
		t.Fatalf("code=%d", code)
	}
}

func TestVerifyDB_OrgOK_EmptyChain(t *testing.T) {
	db, mock := newMockDB(t)
	org := uuid.New()
	expectEmptyLedger(mock, org)
	if code := verifyDB(context.Background(), db, org.String()); code != 0 {
		t.Fatalf("code=%d", code)
	}
}

func TestVerifyDB_SetConfigFail(t *testing.T) {
	db, mock := newMockDB(t)
	org := uuid.New()
	mock.ExpectBegin()
	mock.ExpectExec(`SELECT set_config`).WithArgs(org.String()).
		WillReturnError(context.Canceled)
	mock.ExpectRollback()
	if code := verifyDB(context.Background(), db, org.String()); code != 1 {
		t.Fatalf("code=%d", code)
	}
}

func TestVerifyOrg_ValidRow(t *testing.T) {
	db, mock := newMockDB(t)
	org := uuid.New()
	ts := time.Date(2026, 1, 1, 0, 0, 0, 0, time.UTC)
	e := privacyaudit.Entry{
		OrgID: org, Seq: 1, PrevHash: privacyaudit.GenesisPrevHash, Action: "a",
		Payload: json.RawMessage(`{}`), CreatedAt: ts,
	}
	h, err := privacyaudit.RowHash(e)
	if err != nil {
		t.Fatal(err)
	}
	e.RowHash = h
	expectSetOrgTx(mock, org)
	mock.ExpectQuery("SELECT org_id, seq").WithArgs(org).WillReturnRows(sqlmock.NewRows(entryColumns()).AddRow(
		org, int64(1), privacyaudit.GenesisPrevHash, h,
		nil, "a", "", "",
		"", "", pq.StringArray{},
		"", "", "",
		"", "", []byte(`{}`), ts,
	))
	mock.ExpectCommit()
	n, verr := VerifyOrg(context.Background(), db, org)
	if verr != nil || n != 1 {
		t.Fatalf("n=%d err=%v", n, verr)
	}
}

func TestVerifyDSN_BadOrgFilter(t *testing.T) {
	db, mock := newMockDB(t)
	_ = mock
	if code := verifyDB(context.Background(), db, "bad"); code != 2 {
		t.Fatalf("code=%d", code)
	}
}
