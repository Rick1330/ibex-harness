package privacyaudit

import (
	"context"
	"database/sql"
	"encoding/json"
	"testing"
	"time"

	"github.com/DATA-DOG/go-sqlmock"
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

func addEntryRow(rows *sqlmock.Rows, e Entry, actor any, fields pq.StringArray, payload []byte) *sqlmock.Rows {
	return rows.AddRow(
		e.OrgID, e.Seq, e.PrevHash, e.RowHash,
		actor, e.Action, e.Purpose, e.PolicyResult,
		e.ObjectType, e.ObjectID, fields,
		e.ApprovalRef, e.BeforeHash, e.AfterHash,
		e.CorrelationID, e.RequestID, payload, e.CreatedAt,
	)
}

func expectLoadEntries(mock sqlmock.Sqlmock, org uuid.UUID, rows *sqlmock.Rows) {
	mock.ExpectQuery("SELECT org_id, seq, prev_hash").
		WithArgs(org).
		WillReturnRows(rows)
}

func TestLoadEntries_AndVerifyOrg(t *testing.T) {
	t.Parallel()
	db, mock := newMockDB(t)
	org := uuid.MustParse("55555555-5555-5555-5555-555555555555")
	ts := time.Date(2026, 1, 1, 0, 0, 0, 0, time.UTC)
	e := hashedEntry(t, Entry{
		OrgID: org, Seq: 1, PrevHash: GenesisPrevHash, Action: "a",
		Payload: json.RawMessage(`{}`), CreatedAt: ts,
	})
	rows := addEntryRow(sqlmock.NewRows(entryColumns()), e, nil, pq.StringArray{}, []byte(`{}`))
	expectLoadEntries(mock, org, rows)

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
	db, mock := newMockDB(t)
	org := uuid.MustParse("66666666-6666-6666-6666-666666666666")
	mock.ExpectQuery("SELECT DISTINCT org_id").
		WillReturnRows(sqlmock.NewRows([]string{"org_id"}).AddRow(org))
	got, err := ResolveOrgs(context.Background(), db, "")
	if err != nil {
		t.Fatal(err)
	}
	if len(got) != 1 || got[0] != org {
		t.Fatalf("got=%v", got)
	}
}

func TestLoadEntries_QueryError(t *testing.T) {
	t.Parallel()
	db, mock := newMockDB(t)
	org := uuid.New()
	mock.ExpectQuery("SELECT org_id, seq").WillReturnError(context.Canceled)
	_, err := LoadEntries(context.Background(), db, org)
	if err == nil {
		t.Fatal("expected error")
	}
}

func TestVerifyOrg_ChainBreak(t *testing.T) {
	t.Parallel()
	db, mock := newMockDB(t)
	org := uuid.New()
	ts := time.Now().UTC()
	e := Entry{
		OrgID: org, Seq: 1, PrevHash: GenesisPrevHash, Action: "a",
		RowHash: "badhash", Payload: json.RawMessage(`{}`), CreatedAt: ts,
	}
	rows := addEntryRow(sqlmock.NewRows(entryColumns()), e, nil, pq.StringArray{}, []byte(`{}`))
	expectLoadEntries(mock, org, rows)
	_, err := VerifyOrg(context.Background(), db, org)
	if BreakIndex(err) != 0 {
		t.Fatalf("err=%v", err)
	}
}

func TestLoadEntries_WithActor(t *testing.T) {
	t.Parallel()
	db, mock := newMockDB(t)
	org := uuid.New()
	actor := uuid.New()
	ts := time.Date(2026, 2, 2, 2, 2, 2, 0, time.UTC)
	e := hashedEntry(t, Entry{
		OrgID: org, Seq: 1, PrevHash: GenesisPrevHash, ActorUserID: &actor,
		Action: "x", Fields: []string{"a", "b"}, Payload: json.RawMessage(`{}`), CreatedAt: ts,
	})
	rows := addEntryRow(sqlmock.NewRows(entryColumns()), e, actor.String(), pq.StringArray{"b", "a"}, []byte(`{}`))
	expectLoadEntries(mock, org, rows)
	entries, err := LoadEntries(context.Background(), db, org)
	if err != nil {
		t.Fatal(err)
	}
	if len(entries) != 1 || entries[0].ActorUserID == nil {
		t.Fatalf("entries=%v", entries)
	}
}

func TestListDistinctOrgs_QueryError(t *testing.T) {
	t.Parallel()
	db, mock := newMockDB(t)
	mock.ExpectQuery("SELECT DISTINCT org_id").WillReturnError(context.Canceled)
	_, err := ResolveOrgs(context.Background(), db, "")
	if err == nil {
		t.Fatal("expected error")
	}
}

func TestVerifyOrg_LoadError(t *testing.T) {
	t.Parallel()
	db, mock := newMockDB(t)
	org := uuid.New()
	mock.ExpectQuery("SELECT org_id, seq").WillReturnError(context.Canceled)
	_, err := VerifyOrg(context.Background(), db, org)
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
	db, mock := newMockDB(t)
	org := uuid.New()
	rows := sqlmock.NewRows(entryColumns()).AddRow(
		org, "not-int", GenesisPrevHash, "h",
		nil, "a", "", "",
		"", "", pq.StringArray{},
		"", "", "",
		"", "", []byte(`{}`), time.Now().UTC(),
	)
	expectLoadEntries(mock, org, rows)
	_, err := LoadEntries(context.Background(), db, org)
	if err == nil {
		t.Fatal("expected scan error")
	}
}

func TestScanUUIDs_ScanError(t *testing.T) {
	t.Parallel()
	db, mock := newMockDB(t)
	mock.ExpectQuery("SELECT DISTINCT org_id").
		WillReturnRows(sqlmock.NewRows([]string{"org_id"}).AddRow("not-a-uuid"))
	_, err := ResolveOrgs(context.Background(), db, "")
	if err == nil {
		t.Fatal("expected scan error")
	}
}

func TestSetCurrentOrgID(t *testing.T) {
	t.Parallel()
	db, mock := newMockDB(t)
	org := uuid.MustParse("77777777-7777-7777-7777-777777777777")
	mock.ExpectExec(`SELECT set_config`).WithArgs(org.String()).
		WillReturnResult(sqlmock.NewResult(0, 1))
	if err := SetCurrentOrgID(context.Background(), db, org); err != nil {
		t.Fatal(err)
	}
}

func TestSetCurrentOrgID_Error(t *testing.T) {
	t.Parallel()
	db, mock := newMockDB(t)
	org := uuid.New()
	mock.ExpectExec(`SELECT set_config`).WithArgs(org.String()).
		WillReturnError(context.Canceled)
	if err := SetCurrentOrgID(context.Background(), db, org); err == nil {
		t.Fatal("expected error")
	}
}
