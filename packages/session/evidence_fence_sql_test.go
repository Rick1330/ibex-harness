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

func TestLookupEvidenceFence_ReturnsAuthoritativeVersion(t *testing.T) {
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = db.Close() }()
	store := &PostgresStore{db: db}
	orgID, sessionID := uuid.New(), uuid.New()
	mock.ExpectBegin()
	mock.ExpectExec(`SET LOCAL ROLE ibex_app`).WillReturnResult(sqlmock.NewResult(0, 0))
	mock.ExpectExec(`SELECT set_config`).WithArgs(orgID.String()).WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectQuery(`SELECT evidence_fence_version`).WithArgs(orgID, sessionID).
		WillReturnRows(sqlmock.NewRows([]string{"evidence_fence_version"}).AddRow(int64(7)))
	mock.ExpectCommit()
	got, err := store.LookupEvidenceFence(context.Background(), orgID, sessionID)
	if err != nil {
		t.Fatalf("LookupEvidenceFence: %v", err)
	}
	if got.ResourceType != "session" || got.ResourceID != sessionID || got.ResourceVersion != 7 {
		t.Fatalf("fence=%+v", got)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestLookupEvidenceFence_RejectsNonPositiveVersion(t *testing.T) {
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = db.Close() }()
	store := &PostgresStore{db: db}
	orgID, sessionID := uuid.New(), uuid.New()
	mock.ExpectBegin()
	mock.ExpectExec(`SET LOCAL ROLE ibex_app`).WillReturnResult(sqlmock.NewResult(0, 0))
	mock.ExpectExec(`SELECT set_config`).WithArgs(orgID.String()).WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectQuery(`SELECT evidence_fence_version`).WithArgs(orgID, sessionID).
		WillReturnRows(sqlmock.NewRows([]string{"evidence_fence_version"}).AddRow(int64(0)))
	mock.ExpectRollback()
	if _, err := store.LookupEvidenceFence(context.Background(), orgID, sessionID); err == nil {
		t.Fatal("non-positive fence version accepted")
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestLookupEvidenceFence_FailsClosedOnMissingRow(t *testing.T) {
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = db.Close() }()
	store := &PostgresStore{db: db}
	orgID, sessionID := uuid.New(), uuid.New()
	mock.ExpectBegin()
	mock.ExpectExec(`SET LOCAL ROLE ibex_app`).WillReturnResult(sqlmock.NewResult(0, 0))
	mock.ExpectExec(`SELECT set_config`).WithArgs(orgID.String()).WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectQuery(`SELECT evidence_fence_version`).WithArgs(orgID, sessionID).
		WillReturnError(sql.ErrNoRows)
	mock.ExpectRollback()
	if _, err := store.LookupEvidenceFence(context.Background(), orgID, sessionID); err != ErrEvidenceFenceNotFound {
		t.Fatalf("error=%v want %v", err, ErrEvidenceFenceNotFound)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

// TestLookupEvidenceFence_RoleDeniedFailsClosed covers the pin itself: a login
// that may not assume ibex_app must fail the read rather than run it unscoped.
func TestLookupEvidenceFence_RoleDeniedFailsClosed(t *testing.T) {
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = db.Close() }()
	store := &PostgresStore{db: db}
	orgID, sessionID := uuid.New(), uuid.New()
	mock.ExpectBegin()
	mock.ExpectExec(`SET LOCAL ROLE ibex_app`).
		WillReturnError(&pq.Error{Code: "42501", Message: `permission denied to set role "ibex_app"`})
	mock.ExpectRollback()
	if _, err := store.LookupEvidenceFence(context.Background(), orgID, sessionID); err == nil {
		t.Fatal("fence lookup accepted a denied role pin")
	} else if !isPermissionDenied(err) {
		t.Fatalf("error=%v want a wrapped 42501", err)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func isPermissionDenied(err error) bool {
	var pqErr *pq.Error
	return errors.As(err, &pqErr) && pqErr.Code == "42501"
}
