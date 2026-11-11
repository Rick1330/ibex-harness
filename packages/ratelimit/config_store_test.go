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

// requireOrgOverride checks the org-level RPM a successful load returned.
func requireOrgOverride(t *testing.T, set OrgOverrideSet, want int64) {
	t.Helper()
	if set.OrgRPM == nil || *set.OrgRPM != want {
		t.Fatalf("org RPM=%v want %d", set.OrgRPM, want)
	}
}

// requireAgentOverride checks one agent-level RPM a successful load returned.
func requireAgentOverride(t *testing.T, set OrgOverrideSet, agent uuid.UUID, want int64) {
	t.Helper()
	if got := set.AgentRPM[agent]; got != want {
		t.Fatalf("agent RPM=%d want %d", got, want)
	}
}

// loadTarget parameterises the two ConfigStore loads so one driver covers
// both: whether the transaction pins before it reads, where the read goes, and
// how a failed read's result must look. Each case keeps its own test function,
// so a failure still names the case.
type loadTarget[T any] struct {
	pinOrg       bool
	queryPattern string
	load         func(*ConfigStore, uuid.UUID) (T, error)
	// empty reports whether result is the shape a failed read must return:
	// something a caller cannot mistake for a real snapshot.
	empty func(T) bool
}

var loadOrgTarget = loadTarget[OrgOverrideSet]{
	pinOrg:       true,
	queryPattern: `rate_limit_overrides`,
	load: func(store *ConfigStore, org uuid.UUID) (OrgOverrideSet, error) {
		return store.LoadOrg(context.Background(), org)
	},
	empty: func(set OrgOverrideSet) bool {
		return set.OrgRPM == nil && len(set.AgentRPM) == 0
	},
}

var loadAllTarget = loadTarget[map[uuid.UUID]OrgOverrideSet]{
	queryPattern: `rate_limit_overrides_snapshot`,
	load: func(store *ConfigStore, _ uuid.UUID) (map[uuid.UUID]OrgOverrideSet, error) {
		return store.LoadAll(context.Background())
	},
	empty: func(all map[uuid.UUID]OrgOverrideSet) bool {
		return all == nil
	},
}

// expectLoadOrgPin matches the two statements LoadOrg runs before its read: the
// role pin that makes the capability login usable, then the tenant GUC that
// scopes RLS.
func expectLoadOrgPin(mock sqlmock.Sqlmock, org uuid.UUID) {
	mock.ExpectExec(`SET LOCAL ROLE ibex_app`).WillReturnResult(sqlmock.NewResult(0, 0))
	mock.ExpectExec(`SELECT set_config`).WithArgs(org.String()).WillReturnResult(sqlmock.NewResult(0, 1))
}

// loadFailureSetup is one failing load: which database interaction breaks.
type loadFailureSetup struct {
	label     string
	query     *sqlmock.Rows
	queryErr  error
	commitErr error
}

// expectReadEither arms the snapshot read to fail with queryErr, or to return
// the configured rows.
func expectReadEither(query *sqlmock.ExpectedQuery, setup loadFailureSetup) {
	if setup.queryErr != nil {
		query.WillReturnError(setup.queryErr)
		return
	}
	query.WillReturnRows(setup.query)
}

// expectEndEither arms the transaction to fail at Commit, or to Rollback.
func expectEndEither(mock sqlmock.Sqlmock, commitErr error) {
	if commitErr != nil {
		mock.ExpectCommit().WillReturnError(commitErr)
		return
	}
	mock.ExpectRollback()
}

// runLoadFailure drives one failing load against target: the Begin/pin/read/
// Commit-or-Rollback plumbing, then the two postconditions a failed load owes
// its caller (an error, and the empty result shape).
func runLoadFailure[T any](t *testing.T, target loadTarget[T], setup loadFailureSetup) {
	t.Helper()
	store, mock := newMockConfigStore(t)
	org := uuid.New()
	mock.ExpectBegin()
	if target.pinOrg {
		expectLoadOrgPin(mock, org)
	}
	expectReadEither(mock.ExpectQuery(target.queryPattern), setup)
	expectEndEither(mock, setup.commitErr)

	result, err := target.load(store, org)
	if err == nil {
		t.Fatalf("%s: returned no error; the caller would see no overrides", setup.label)
	}
	if !target.empty(result) {
		t.Fatalf("%s: returned %+v; caller could read it as no overrides", setup.label, result)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

// runLoadSuccess performs one successful load and returns its result for the
// caller's assertions. org is only bound for the pinning load; a target with no
// pin ignores it.
func runLoadSuccess[T any](t *testing.T, target loadTarget[T], org uuid.UUID, rows *sqlmock.Rows) T {
	t.Helper()
	store, mock := newMockConfigStore(t)
	mock.ExpectBegin()
	if target.pinOrg {
		expectLoadOrgPin(mock, org)
	}
	query := mock.ExpectQuery(target.queryPattern)
	if target.pinOrg {
		query = query.WithArgs(org)
	}
	query.WillReturnRows(rows)
	mock.ExpectCommit()

	result, err := target.load(store, org)
	if err != nil {
		t.Fatalf("load: %v", err)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
	return result
}

// pinStep names the statement in LoadOrg's pin sequence that a failure case
// breaks.
type pinStep int

const (
	pinRole pinStep = iota
	pinOrgGUC
)

func (s pinStep) String() string {
	if s == pinRole {
		return "the role pin"
	}
	return "the org GUC"
}

// runPinFailure drives LoadOrg until the chosen pin statement fails and
// requires the error to name that step.
func runPinFailure(t *testing.T, step pinStep, want string) {
	t.Helper()
	store, mock := newMockConfigStore(t)
	org := uuid.New()
	mock.ExpectBegin()
	if step == pinRole {
		mock.ExpectExec(`SET LOCAL ROLE ibex_app`).WillReturnError(sql.ErrConnDone)
	} else {
		mock.ExpectExec(`SET LOCAL ROLE ibex_app`).WillReturnResult(sqlmock.NewResult(0, 0))
		mock.ExpectExec(`SELECT set_config`).WithArgs(org.String()).WillReturnError(sql.ErrConnDone)
	}
	mock.ExpectRollback()

	set, err := store.LoadOrg(context.Background(), org)
	if err == nil {
		t.Fatalf("%s failed but LoadOrg returned no error; the caller would see an empty override set", step)
	}
	if !strings.Contains(err.Error(), want) {
		t.Fatalf("error %q does not identify %s", err, want)
	}
	requireEmptyOverrideSet(t, set)
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestConfigStore_LoadOrg_RolePinError(t *testing.T) {
	t.Parallel()
	runPinFailure(t, pinRole, "set tenant role")
}

func TestConfigStore_LoadOrg_PinError(t *testing.T) {
	t.Parallel()
	runPinFailure(t, pinOrgGUC, "set rls")
}

func TestConfigStore_LoadOrg_ReturnsOrgOverrides(t *testing.T) {
	t.Parallel()
	org, agent := uuid.New(), uuid.New()
	set := runLoadSuccess(t, loadOrgTarget, org, overrideRows().
		AddRow(org.String(), nil, int64(120)).
		AddRow(org.String(), agent.String(), int64(60)))
	requireOrgOverride(t, set, 120)
	requireAgentOverride(t, set, agent, 60)
}

// TestConfigStore_LoadOrg_NoOverrides proves a pinned read that finds nothing
// returns an empty set rather than an error: "no override" is a valid answer.
func TestConfigStore_LoadOrg_NoOverrides(t *testing.T) {
	t.Parallel()
	set := runLoadSuccess(t, loadOrgTarget, uuid.New(), overrideRows())
	requireEmptyOverrideSet(t, set)
}

func TestConfigStore_LoadOrg_QueryError(t *testing.T) {
	t.Parallel()
	runLoadFailure(t, loadOrgTarget, loadFailureSetup{label: "query failure", queryErr: sql.ErrConnDone})
}

func TestConfigStore_LoadOrg_ScanError(t *testing.T) {
	t.Parallel()
	runLoadFailure(t, loadOrgTarget, loadFailureSetup{
		label: "scan failure",
		query: overrideRows().AddRow("not-a-uuid", nil, int64(111)),
	})
}

func TestConfigStore_LoadOrg_RowsError(t *testing.T) {
	t.Parallel()
	runLoadFailure(t, loadOrgTarget, loadFailureSetup{
		label: "row iteration failure",
		query: overrideRows().AddRow(uuid.New().String(), nil, int64(111)).RowError(0, sql.ErrConnDone),
	})
}

func TestConfigStore_LoadOrg_CommitError(t *testing.T) {
	t.Parallel()
	runLoadFailure(t, loadOrgTarget, loadFailureSetup{
		label:     "commit failure",
		query:     overrideRows().AddRow(uuid.New().String(), nil, int64(111)),
		commitErr: sql.ErrTxDone,
	})
}

// LoadAll intentionally has no pin: it reads the cross-tenant definer, so its
// failure modes are the query and the commit. Both must surface as errors rather
// than an empty map.
func TestConfigStore_LoadAll_ReturnsAllOverrides(t *testing.T) {
	t.Parallel()
	orgA, orgB, agentB := uuid.New(), uuid.New(), uuid.New()
	all := runLoadSuccess(t, loadAllTarget, uuid.Nil, overrideRows().
		AddRow(orgA.String(), nil, int64(111)).
		AddRow(orgB.String(), agentB.String(), int64(222)))
	requireOrgOverride(t, all[orgA], 111)
	requireAgentOverride(t, all[orgB], agentB, 222)
}

func TestConfigStore_LoadAll_QueryError(t *testing.T) {
	t.Parallel()
	runLoadFailure(t, loadAllTarget, loadFailureSetup{label: "query failure", queryErr: sql.ErrConnDone})
}

func TestConfigStore_LoadAll_ScanError(t *testing.T) {
	t.Parallel()
	runLoadFailure(t, loadAllTarget, loadFailureSetup{
		label: "scan failure",
		query: overrideRows().AddRow("not-a-uuid", nil, int64(111)),
	})
}

func TestConfigStore_LoadAll_RowsError(t *testing.T) {
	t.Parallel()
	runLoadFailure(t, loadAllTarget, loadFailureSetup{
		label: "row iteration failure",
		query: overrideRows().AddRow(uuid.New().String(), nil, int64(111)).RowError(0, sql.ErrConnDone),
	})
}

func TestConfigStore_LoadAll_CommitError(t *testing.T) {
	t.Parallel()
	runLoadFailure(t, loadAllTarget, loadFailureSetup{
		label:     "commit failure",
		query:     overrideRows().AddRow(uuid.New().String(), nil, int64(111)),
		commitErr: sql.ErrTxDone,
	})
}
