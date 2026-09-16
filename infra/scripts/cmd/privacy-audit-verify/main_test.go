package main

import (
	"context"
	"testing"
	"time"

	"github.com/DATA-DOG/go-sqlmock"
	"github.com/Rick1330/ibex-harness/packages/privacyaudit"
	"github.com/google/uuid"
	"github.com/lib/pq"
)

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
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = db.Close() })
	mock.ExpectQuery("SELECT DISTINCT org_id").
		WillReturnRows(sqlmock.NewRows([]string{"org_id"}))
	if code := verifyDB(context.Background(), db, ""); code != 0 {
		t.Fatalf("code=%d", code)
	}
}

func TestVerifyDB_ListError(t *testing.T) {
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = db.Close() })
	mock.ExpectQuery("SELECT DISTINCT org_id").WillReturnError(context.Canceled)
	if code := verifyDB(context.Background(), db, ""); code != 2 {
		t.Fatalf("code=%d", code)
	}
}

func TestVerifyDB_ChainFail(t *testing.T) {
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = db.Close() })
	org := uuid.New()
	ts := time.Now().UTC()
	mock.ExpectQuery("SELECT org_id, seq").WithArgs(org).WillReturnRows(sqlmock.NewRows([]string{
		"org_id", "seq", "prev_hash", "row_hash",
		"actor_user_id", "action", "purpose", "policy_result",
		"object_type", "object_id", "fields",
		"approval_ref", "before_hash", "after_hash",
		"correlation_id", "request_id", "payload", "created_at",
	}).AddRow(
		org, int64(1), privacyaudit.GenesisPrevHash, "bad",
		nil, "a", "", "",
		"", "", pq.StringArray{},
		"", "", "",
		"", "", []byte(`{}`), ts,
	))
	if code := verifyDB(context.Background(), db, org.String()); code != 1 {
		t.Fatalf("code=%d", code)
	}
}

func TestVerifyDB_OrgOK(t *testing.T) {
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = db.Close() })
	org := uuid.New()
	mock.ExpectQuery("SELECT org_id, seq").WithArgs(org).
		WillReturnRows(sqlmock.NewRows([]string{
			"org_id", "seq", "prev_hash", "row_hash",
			"actor_user_id", "action", "purpose", "policy_result",
			"object_type", "object_id", "fields",
			"approval_ref", "before_hash", "after_hash",
			"correlation_id", "request_id", "payload", "created_at",
		}))
	if code := verifyDB(context.Background(), db, org.String()); code != 0 {
		t.Fatalf("code=%d", code)
	}
}

func TestVerifyDSN_BadDriverOpen(t *testing.T) {
	// sql.Open with empty driver name isn't available; invalid DSN still opens.
	// Cover open error path is rare — exercise parse failure via org filter instead.
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = db.Close() })
	_ = mock
	if code := verifyDB(context.Background(), db, "bad"); code != 2 {
		t.Fatalf("code=%d", code)
	}
}
