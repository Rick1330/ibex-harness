package privacyaudit

import (
	"context"
	"encoding/json"
	"testing"
	"time"

	"github.com/DATA-DOG/go-sqlmock"
	"github.com/google/uuid"
	"github.com/lib/pq"
)

func TestLoadEntries_AndVerifyOrg(t *testing.T) {
	t.Parallel()
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = db.Close() })

	org := uuid.MustParse("55555555-5555-5555-5555-555555555555")
	ts := time.Date(2026, 1, 1, 0, 0, 0, 0, time.UTC)
	e := Entry{
		OrgID: org, Seq: 1, PrevHash: GenesisPrevHash, Action: "a",
		Payload: json.RawMessage(`{}`), CreatedAt: ts,
	}
	h, err := RowHash(e)
	if err != nil {
		t.Fatal(err)
	}

	rows := sqlmock.NewRows([]string{
		"org_id", "seq", "prev_hash", "row_hash",
		"actor_user_id", "action", "purpose", "policy_result",
		"object_type", "object_id", "fields",
		"approval_ref", "before_hash", "after_hash",
		"correlation_id", "request_id", "payload", "created_at",
	}).AddRow(
		org, int64(1), GenesisPrevHash, h,
		nil, "a", "", "",
		"", "", pq.StringArray{},
		"", "", "",
		"", "", []byte(`{}`), ts,
	)
	mock.ExpectQuery("SELECT org_id, seq, prev_hash").
		WithArgs(org).
		WillReturnRows(rows)

	n, err := VerifyOrg(context.Background(), db, org)
	if err != nil || n != 1 {
		t.Fatalf("n=%d err=%v", n, err)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestResolveOrgs_Distinct(t *testing.T) {
	t.Parallel()
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = db.Close() })
	org := uuid.MustParse("66666666-6666-6666-6666-666666666666")
	mock.ExpectQuery("SELECT DISTINCT org_id").
		WillReturnRows(sqlmock.NewRows([]string{"org_id"}).AddRow(org))
	got, err := ResolveOrgs(context.Background(), db, "")
	if err != nil || len(got) != 1 || got[0] != org {
		t.Fatalf("got=%v err=%v", got, err)
	}
}

func TestLoadEntries_QueryError(t *testing.T) {
	t.Parallel()
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = db.Close() })
	org := uuid.New()
	mock.ExpectQuery("SELECT org_id, seq").WillReturnError(context.Canceled)
	_, err = LoadEntries(context.Background(), db, org)
	if err == nil {
		t.Fatal("expected error")
	}
}

func TestVerifyOrg_ChainBreak(t *testing.T) {
	t.Parallel()
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = db.Close() })
	org := uuid.New()
	ts := time.Now().UTC()
	rows := sqlmock.NewRows([]string{
		"org_id", "seq", "prev_hash", "row_hash",
		"actor_user_id", "action", "purpose", "policy_result",
		"object_type", "object_id", "fields",
		"approval_ref", "before_hash", "after_hash",
		"correlation_id", "request_id", "payload", "created_at",
	}).AddRow(
		org, int64(1), GenesisPrevHash, "badhash",
		nil, "a", "", "",
		"", "", pq.StringArray{},
		"", "", "",
		"", "", []byte(`{}`), ts,
	)
	mock.ExpectQuery("SELECT org_id, seq").WithArgs(org).WillReturnRows(rows)
	_, err = VerifyOrg(context.Background(), db, org)
	if BreakIndex(err) != 0 {
		t.Fatalf("err=%v", err)
	}
}

func TestLoadEntries_WithActor(t *testing.T) {
	t.Parallel()
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = db.Close() })
	org := uuid.New()
	actor := uuid.New()
	ts := time.Date(2026, 2, 2, 2, 2, 2, 0, time.UTC)
	e := Entry{
		OrgID: org, Seq: 1, PrevHash: GenesisPrevHash, ActorUserID: &actor,
		Action: "x", Payload: json.RawMessage(`{}`), CreatedAt: ts,
	}
	h, _ := RowHash(e)
	rows := sqlmock.NewRows([]string{
		"org_id", "seq", "prev_hash", "row_hash",
		"actor_user_id", "action", "purpose", "policy_result",
		"object_type", "object_id", "fields",
		"approval_ref", "before_hash", "after_hash",
		"correlation_id", "request_id", "payload", "created_at",
	}).AddRow(
		org, int64(1), GenesisPrevHash, h,
		actor.String(), "x", "", "",
		"", "", pq.StringArray{"b", "a"},
		"", "", "",
		"", "", []byte(`{}`), ts,
	)
	mock.ExpectQuery("SELECT org_id, seq").WithArgs(org).WillReturnRows(rows)
	entries, err := LoadEntries(context.Background(), db, org)
	if err != nil || len(entries) != 1 || entries[0].ActorUserID == nil {
		t.Fatalf("entries=%v err=%v", entries, err)
	}
}

func TestListDistinctOrgs_QueryError(t *testing.T) {
	t.Parallel()
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = db.Close() })
	mock.ExpectQuery("SELECT DISTINCT org_id").WillReturnError(context.Canceled)
	_, err = ResolveOrgs(context.Background(), db, "")
	if err == nil {
		t.Fatal("expected error")
	}
}

func TestVerifyOrg_LoadError(t *testing.T) {
	t.Parallel()
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = db.Close() })
	org := uuid.New()
	mock.ExpectQuery("SELECT org_id, seq").WillReturnError(context.Canceled)
	_, err = VerifyOrg(context.Background(), db, org)
	if err == nil {
		t.Fatal("expected error")
	}
}

func TestChainBreak_WithErr(t *testing.T) {
	t.Parallel()
	b := &ChainBreak{Err: fmtError("boom")}
	if b.Error() != "boom" {
		t.Fatalf("%q", b.Error())
	}
}

func TestCanonicalString_InvalidPayload(t *testing.T) {
	t.Parallel()
	_, err := CanonicalString(Entry{
		OrgID: uuid.New(), Seq: 1, PrevHash: GenesisPrevHash,
		Action: "a", Payload: json.RawMessage(`{`), CreatedAt: time.Now().UTC(),
	})
	if err == nil {
		t.Fatal("expected error")
	}
}

func TestRowHash_InvalidPayload(t *testing.T) {
	t.Parallel()
	_, err := RowHash(Entry{
		OrgID: uuid.New(), Seq: 1, PrevHash: GenesisPrevHash,
		Action: "a", Payload: json.RawMessage(`{`), CreatedAt: time.Now().UTC(),
	})
	if err == nil {
		t.Fatal("expected error")
	}
}

func TestScanEntries_ScanError(t *testing.T) {
	t.Parallel()
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = db.Close() })
	org := uuid.New()
	// Wrong type for seq triggers scan error.
	rows := sqlmock.NewRows([]string{
		"org_id", "seq", "prev_hash", "row_hash",
		"actor_user_id", "action", "purpose", "policy_result",
		"object_type", "object_id", "fields",
		"approval_ref", "before_hash", "after_hash",
		"correlation_id", "request_id", "payload", "created_at",
	}).AddRow(
		org, "not-int", GenesisPrevHash, "h",
		nil, "a", "", "",
		"", "", pq.StringArray{},
		"", "", "",
		"", "", []byte(`{}`), time.Now().UTC(),
	)
	mock.ExpectQuery("SELECT org_id, seq").WithArgs(org).WillReturnRows(rows)
	_, err = LoadEntries(context.Background(), db, org)
	if err == nil {
		t.Fatal("expected scan error")
	}
}

func TestScanUUIDs_ScanError(t *testing.T) {
	t.Parallel()
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = db.Close() })
	mock.ExpectQuery("SELECT DISTINCT org_id").
		WillReturnRows(sqlmock.NewRows([]string{"org_id"}).AddRow("not-a-uuid"))
	_, err = ResolveOrgs(context.Background(), db, "")
	if err == nil {
		t.Fatal("expected scan error")
	}
}
