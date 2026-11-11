package ratelimit

import (
	"context"
	"database/sql"
	"strings"
	"testing"

	"github.com/DATA-DOG/go-sqlmock"
	"github.com/google/uuid"
)

func newMockConfigStore(t *testing.T) (*ConfigStore, sqlmock.Sqlmock) {
	t.Helper()
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = db.Close() })
	store, err := NewConfigStore(db)
	if err != nil {
		t.Fatal(err)
	}
	return store, mock
}

func overrideRows() *sqlmock.Rows {
	return sqlmock.NewRows([]string{"org_id", "agent_id", "requests_per_minute"})
}

// requireEmptyOverrideSet proves a failed pin/read cannot be read as "no
// overrides": both are an empty OrgOverrideSet.
func requireEmptyOverrideSet(t *testing.T, set OrgOverrideSet) {
	t.Helper()
	if set.OrgRPM != nil || len(set.AgentRPM) != 0 {
		t.Fatalf("failed read returned overrides %+v; caller could mistake it for an empty snapshot", set)
	}
}

func TestConfigStore_LoadOrg_PinError(t *testing.T) {
	t.Parallel()
	store, mock := newMockConfigStore(t)
	org := uuid.New()
	mock.ExpectBegin()
	mock.ExpectExec(`SELECT set_config`).WithArgs(org.String()).WillReturnError(sql.ErrConnDone)
	mock.ExpectRollback()

	set, err := store.LoadOrg(context.Background(), org)
	if err == nil {
		t.Fatal("org-GUC failure returned no error; the caller would see an empty override set")
	}
	if !strings.Contains(err.Error(), "set rls") {
		t.Fatalf("error %q does not identify the org GUC", err)
	}
	requireEmptyOverrideSet(t, set)
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestConfigStore_LoadOrg_ReturnsOrgOverrides(t *testing.T) {
	t.Parallel()
	store, mock := newMockConfigStore(t)
	org, agent := uuid.New(), uuid.New()
	mock.ExpectBegin()
	mock.ExpectExec(`SELECT set_config`).WithArgs(org.String()).WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectQuery(`rate_limit_overrides`).WithArgs(org).WillReturnRows(
		overrideRows().
			AddRow(org.String(), nil, int64(120)).
			AddRow(org.String(), agent.String(), int64(60)))
	mock.ExpectCommit()

	set, err := store.LoadOrg(context.Background(), org)
	if err != nil {
		t.Fatalf("LoadOrg: %v", err)
	}
	if set.OrgRPM == nil || *set.OrgRPM != 120 {
		t.Fatalf("org RPM=%v want 120", set.OrgRPM)
	}
	if got := set.AgentRPM[agent]; got != 60 {
		t.Fatalf("agent RPM=%d want 60", got)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestConfigStore_LoadOrg_QueryError(t *testing.T) {
	t.Parallel()
	store, mock := newMockConfigStore(t)
	org := uuid.New()
	mock.ExpectBegin()
	mock.ExpectExec(`SELECT set_config`).WithArgs(org.String()).WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectQuery(`rate_limit_overrides`).WithArgs(org).WillReturnError(sql.ErrConnDone)
	mock.ExpectRollback()

	set, err := store.LoadOrg(context.Background(), org)
	if err == nil {
		t.Fatal("query failure returned no error; the caller would see an empty override set")
	}
	requireEmptyOverrideSet(t, set)
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

// LoadAll intentionally has no pin: it reads the cross-tenant definer, so its
// failure modes are the query and the commit. Both must surface as errors rather
// than an empty map.
func TestConfigStore_LoadAll_ReturnsAllOverrides(t *testing.T) {
	t.Parallel()
	store, mock := newMockConfigStore(t)
	orgA, orgB, agentB := uuid.New(), uuid.New(), uuid.New()
	mock.ExpectBegin()
	mock.ExpectQuery(`rate_limit_overrides_snapshot`).WillReturnRows(
		overrideRows().
			AddRow(orgA.String(), nil, int64(111)).
			AddRow(orgB.String(), agentB.String(), int64(222)))
	mock.ExpectCommit()

	all, err := store.LoadAll(context.Background())
	if err != nil {
		t.Fatalf("LoadAll: %v", err)
	}
	if got := all[orgA].OrgRPM; got == nil || *got != 111 {
		t.Fatalf("org A RPM=%v want 111", got)
	}
	if got := all[orgB].AgentRPM[agentB]; got != 222 {
		t.Fatalf("org B agent RPM=%d want 222", got)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

type loadAllFailureSetup struct {
	label     string
	query     *sqlmock.Rows
	queryErr  error
	commitErr error
}

// runLoadAllFailure drives one LoadAll failure case. The caller keeps its own
// test function, so a failure names the case; this helper only shares the
// Begin/Query/Commit-or-Rollback plumbing the four cases have in common.
func runLoadAllFailure(t *testing.T, setup loadAllFailureSetup) {
	t.Helper()
	store, mock := newMockConfigStore(t)
	mock.ExpectBegin()
	query := mock.ExpectQuery(`rate_limit_overrides_snapshot`)
	if setup.queryErr != nil {
		query.WillReturnError(setup.queryErr)
	} else {
		query.WillReturnRows(setup.query)
	}
	if setup.commitErr != nil {
		mock.ExpectCommit().WillReturnError(setup.commitErr)
	} else {
		mock.ExpectRollback()
	}

	all, err := store.LoadAll(context.Background())
	if err == nil {
		t.Fatalf("%s: returned no error; the caller would see no overrides", setup.label)
	}
	if all != nil {
		t.Fatalf("%s: returned a map %#v; caller could read it as no overrides", setup.label, all)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestConfigStore_LoadAll_QueryError(t *testing.T) {
	t.Parallel()
	runLoadAllFailure(t, loadAllFailureSetup{label: "query failure", queryErr: sql.ErrConnDone})
}

func TestConfigStore_LoadAll_ScanError(t *testing.T) {
	t.Parallel()
	runLoadAllFailure(t, loadAllFailureSetup{
		label: "scan failure",
		query: overrideRows().AddRow("not-a-uuid", nil, int64(111)),
	})
}

func TestConfigStore_LoadAll_RowsError(t *testing.T) {
	t.Parallel()
	runLoadAllFailure(t, loadAllFailureSetup{
		label: "row iteration failure",
		query: overrideRows().AddRow(uuid.New().String(), nil, int64(111)).RowError(0, sql.ErrConnDone),
	})
}

func TestConfigStore_LoadAll_CommitError(t *testing.T) {
	t.Parallel()
	runLoadAllFailure(t, loadAllFailureSetup{
		label:     "commit failure",
		query:     overrideRows().AddRow(uuid.New().String(), nil, int64(111)),
		commitErr: sql.ErrTxDone,
	})
}
