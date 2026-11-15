package session

import (
	"context"
	"database/sql"
	"errors"
	"testing"

	"github.com/DATA-DOG/go-sqlmock"
	"github.com/google/uuid"
	"github.com/lib/pq"
)

// fenceFixture is one store bound to a sqlmock database, plus the identifiers
// every fence lookup is scoped by.
type fenceFixture struct {
	mock      sqlmock.Sqlmock
	store     *PostgresStore
	orgID     uuid.UUID
	sessionID uuid.UUID
}

func newFenceFixture(t *testing.T) fenceFixture {
	t.Helper()
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = db.Close() })
	return fenceFixture{mock: mock, store: &PostgresStore{db: db}, orgID: uuid.New(), sessionID: uuid.New()}
}

// expectTenantPin queues the role switch and org scope that every scoped read
// opens its transaction with.
func expectTenantPin(mock sqlmock.Sqlmock, orgID uuid.UUID) {
	mock.ExpectBegin()
	mock.ExpectExec(`SET LOCAL ROLE ibex_app`).WillReturnResult(sqlmock.NewResult(0, 0))
	mock.ExpectExec(`SELECT set_config`).WithArgs(orgID.String()).WillReturnResult(sqlmock.NewResult(0, 1))
}

func requireFenceExpectations(t *testing.T, mock sqlmock.Sqlmock) {
	t.Helper()
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestLookupEvidenceFence_ReturnsAuthoritativeVersion(t *testing.T) {
	f := newFenceFixture(t)
	expectTenantPin(f.mock, f.orgID)
	f.mock.ExpectQuery(`SELECT evidence_fence_version`).WithArgs(f.orgID, f.sessionID).
		WillReturnRows(sqlmock.NewRows([]string{"evidence_fence_version"}).AddRow(int64(7)))
	f.mock.ExpectCommit()
	got, err := f.store.LookupEvidenceFence(context.Background(), f.orgID, f.sessionID)
	if err != nil {
		t.Fatalf("LookupEvidenceFence: %v", err)
	}
	if got.ResourceType != "session" || got.ResourceID != f.sessionID || got.ResourceVersion != 7 {
		t.Fatalf("fence=%+v", got)
	}
	requireFenceExpectations(t, f.mock)
}

func TestLookupEvidenceFence_RejectsNonPositiveVersion(t *testing.T) {
	f := newFenceFixture(t)
	expectTenantPin(f.mock, f.orgID)
	f.mock.ExpectQuery(`SELECT evidence_fence_version`).WithArgs(f.orgID, f.sessionID).
		WillReturnRows(sqlmock.NewRows([]string{"evidence_fence_version"}).AddRow(int64(0)))
	f.mock.ExpectRollback()
	if _, err := f.store.LookupEvidenceFence(context.Background(), f.orgID, f.sessionID); err == nil {
		t.Fatal("non-positive fence version accepted")
	}
	requireFenceExpectations(t, f.mock)
}

func TestLookupEvidenceFence_FailsClosedOnMissingRow(t *testing.T) {
	f := newFenceFixture(t)
	expectTenantPin(f.mock, f.orgID)
	f.mock.ExpectQuery(`SELECT evidence_fence_version`).WithArgs(f.orgID, f.sessionID).
		WillReturnError(sql.ErrNoRows)
	f.mock.ExpectRollback()
	if _, err := f.store.LookupEvidenceFence(context.Background(), f.orgID, f.sessionID); err != ErrEvidenceFenceNotFound {
		t.Fatalf("error=%v want %v", err, ErrEvidenceFenceNotFound)
	}
	requireFenceExpectations(t, f.mock)
}

// TestLookupEvidenceFence_RoleDeniedFailsClosed covers the pin itself: a login
// that may not assume ibex_app must fail the read rather than run it unscoped.
func TestLookupEvidenceFence_RoleDeniedFailsClosed(t *testing.T) {
	f := newFenceFixture(t)
	f.mock.ExpectBegin()
	f.mock.ExpectExec(`SET LOCAL ROLE ibex_app`).
		WillReturnError(&pq.Error{Code: "42501", Message: `permission denied to set role "ibex_app"`})
	f.mock.ExpectRollback()
	if _, err := f.store.LookupEvidenceFence(context.Background(), f.orgID, f.sessionID); err == nil {
		t.Fatal("fence lookup accepted a denied role pin")
	} else if !isPermissionDenied(err) {
		t.Fatalf("error=%v want a wrapped 42501", err)
	}
	requireFenceExpectations(t, f.mock)
}

func isPermissionDenied(err error) bool {
	var pqErr *pq.Error
	return errors.As(err, &pqErr) && pqErr.Code == "42501"
}
