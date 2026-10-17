package session

import (
	"context"
	"database/sql"
	"testing"

	"github.com/DATA-DOG/go-sqlmock"
	"github.com/google/uuid"
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
