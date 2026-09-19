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

type entryRowOpts struct {
	entry   Entry
	actor   any
	fields  pq.StringArray
	payload []byte
}

func addEntryRow(rows *sqlmock.Rows, o entryRowOpts) *sqlmock.Rows {
	e := o.entry
	if o.fields == nil {
		o.fields = pq.StringArray{}
	}
	if o.payload == nil {
		o.payload = []byte(`{}`)
	}
	return rows.AddRow(
		e.OrgID, e.Seq, e.PrevHash, e.RowHash,
		o.actor, e.Action, e.Purpose, e.PolicyResult,
		e.ObjectType, e.ObjectID, o.fields,
		e.ApprovalRef, e.BeforeHash, e.AfterHash,
		e.CorrelationID, e.RequestID, o.payload, e.CreatedAt,
	)
}

func expectLoadEntries(mock sqlmock.Sqlmock, org uuid.UUID, rows *sqlmock.Rows) {
	mock.ExpectQuery("SELECT org_id, seq, prev_hash").
		WithArgs(org).
		WillReturnRows(rows)
}

func assertOneOrg(t *testing.T, got []uuid.UUID, want uuid.UUID) {
	t.Helper()
	if len(got) != 1 || got[0] != want {
		t.Fatalf("got=%v want=[%s]", got, want)
	}
}

func assertOneEntryWithActor(t *testing.T, entries []Entry) {
	t.Helper()
	if len(entries) != 1 {
		t.Fatalf("entries len=%d", len(entries))
	}
	if entries[0].ActorUserID == nil {
		t.Fatal("expected actor")
	}
}

func TestLoadEntries_AndVerifyOrg(t *testing.T) {
	t.Parallel()
	db, mock := newMockDB(t)
	org := uuid.MustParse("55555555-5555-5555-5555-555555555555")
	e := hashedEntry(t, baseEntry(baseEntryOpts{org: org}))
	rows := addEntryRow(sqlmock.NewRows(entryColumns()), entryRowOpts{entry: e})
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
	assertOneOrg(t, got, org)
}

func TestVerifyOrg_ChainBreak(t *testing.T) {
	t.Parallel()
	db, mock := newMockDB(t)
	org := uuid.New()
	e := baseEntry(baseEntryOpts{org: org, ts: time.Now().UTC()})
	e.RowHash = "badhash"
	rows := addEntryRow(sqlmock.NewRows(entryColumns()), entryRowOpts{entry: e})
	expectLoadEntries(mock, org, rows)
	_, err := VerifyOrg(context.Background(), db, org)
	assertBreakAt(t, err, 0)
}

func TestLoadEntries_WithActor(t *testing.T) {
	t.Parallel()
	db, mock := newMockDB(t)
	org, actor := uuid.New(), uuid.New()
	ts := time.Date(2026, 2, 2, 2, 2, 2, 0, time.UTC)
	e := hashedEntry(t, baseEntry(baseEntryOpts{
		org: org, actor: &actor, action: "x",
		fields: []string{"a", "b"}, ts: ts,
	}))
	rows := addEntryRow(sqlmock.NewRows(entryColumns()), entryRowOpts{
		entry: e, actor: actor.String(), fields: pq.StringArray{"b", "a"},
	})
	expectLoadEntries(mock, org, rows)
	entries, err := LoadEntries(context.Background(), db, org)
	if err != nil {
		t.Fatal(err)
	}
	assertOneEntryWithActor(t, entries)
}

func TestQueryErrorPaths(t *testing.T) {
	t.Parallel()
	cases := []struct {
		name   string
		expect func(sqlmock.Sqlmock, uuid.UUID)
		run    func(*sql.DB, uuid.UUID) error
	}{
		{
			name: "LoadEntries",
			expect: func(mock sqlmock.Sqlmock, org uuid.UUID) {
				mock.ExpectQuery("SELECT org_id, seq").WillReturnError(context.Canceled)
			},
			run: func(db *sql.DB, org uuid.UUID) error {
				_, err := LoadEntries(context.Background(), db, org)
				return err
			},
		},
		{
			name: "ListDistinctOrgs",
			expect: func(mock sqlmock.Sqlmock, _ uuid.UUID) {
				mock.ExpectQuery("SELECT DISTINCT org_id").WillReturnError(context.Canceled)
			},
			run: func(db *sql.DB, _ uuid.UUID) error {
				_, err := ResolveOrgs(context.Background(), db, "")
				return err
			},
		},
		{
			name: "VerifyOrg",
			expect: func(mock sqlmock.Sqlmock, org uuid.UUID) {
				mock.ExpectQuery("SELECT org_id, seq").WillReturnError(context.Canceled)
			},
			run: func(db *sql.DB, org uuid.UUID) error {
				_, err := VerifyOrg(context.Background(), db, org)
				return err
			},
		},
		{
			name: "SetCurrentOrgID",
			expect: func(mock sqlmock.Sqlmock, org uuid.UUID) {
				mock.ExpectExec(`SELECT set_config`).WithArgs(org.String()).
					WillReturnError(context.Canceled)
			},
			run: func(db *sql.DB, org uuid.UUID) error {
				return SetCurrentOrgID(context.Background(), db, org)
			},
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			db, mock := newMockDB(t)
			org := uuid.New()
			tc.expect(mock, org)
			if err := tc.run(db, org); err == nil {
				t.Fatal("expected error")
			}
		})
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
	_, err := CanonicalString(baseEntry(baseEntryOpts{
		org: uuid.New(), payload: json.RawMessage(`{`), ts: time.Now().UTC(),
	}))
	if err == nil {
		t.Fatal("expected error")
	}
}

func TestRowHash_InvalidPayload(t *testing.T) {
	t.Parallel()
	_, err := RowHash(baseEntry(baseEntryOpts{
		org: uuid.New(), payload: json.RawMessage(`{`), ts: time.Now().UTC(),
	}))
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
