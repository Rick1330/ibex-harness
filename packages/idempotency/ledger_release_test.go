package idempotency

import (
	"context"
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/DATA-DOG/go-sqlmock"
	"github.com/google/uuid"
)

func releaseTestClaim() ClaimToken {
	return ClaimToken{
		ID:        uuid.New(),
		Principal: Principal{OrgID: uuid.New(), AgentID: uuid.New()},
		Key:       "release-key", RequestHash: HashRequest([]byte("release-body")), Version: 3,
	}
}

func TestPostgresLedgerReleaseValidationAndFailures(t *testing.T) {
	ctx := context.Background()
	invalidDB, invalidMock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = invalidDB.Close() })
	ledger, err := NewPostgresLedger(invalidDB, time.Minute)
	if err != nil {
		t.Fatal(err)
	}
	if err := ledger.Release(ctx, ClaimToken{}); !errors.Is(err, ErrInvalidLedgerClaim) {
		t.Fatalf("invalid release error=%v", err)
	}
	if err := invalidMock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}

	claim := releaseTestClaim()
	cases := []struct {
		name  string
		setup func(sqlmock.Sqlmock, ClaimToken)
		want  string
	}{
		{
			name: "begin", setup: func(m sqlmock.Sqlmock, _ ClaimToken) {
				m.ExpectBegin().WillReturnError(errors.New("begin failed"))
			}, want: "begin failed",
		},
		{
			name: "scope", setup: func(m sqlmock.Sqlmock, c ClaimToken) {
				m.ExpectBegin()
				m.ExpectExec(`SELECT set_config`).WithArgs(c.Principal.OrgID.String()).WillReturnError(errors.New("scope failed"))
			}, want: "scope failed",
		},
		{
			name: "delete", setup: func(m sqlmock.Sqlmock, c ClaimToken) {
				m.ExpectBegin()
				m.ExpectExec(`SELECT set_config`).WithArgs(c.Principal.OrgID.String()).WillReturnResult(sqlmock.NewResult(0, 1))
				m.ExpectExec(`DELETE FROM ibex_core\.idempotency_ledger`).WithArgs(c.ID, c.Principal.OrgID, c.Principal.AgentID, c.Key, c.RequestHash, c.Version).WillReturnError(errors.New("delete failed"))
			}, want: "delete failed",
		},
		{
			name: "rows affected", setup: func(m sqlmock.Sqlmock, c ClaimToken) {
				m.ExpectBegin()
				m.ExpectExec(`SELECT set_config`).WithArgs(c.Principal.OrgID.String()).WillReturnResult(sqlmock.NewResult(0, 1))
				m.ExpectExec(`DELETE FROM ibex_core\.idempotency_ledger`).WithArgs(c.ID, c.Principal.OrgID, c.Principal.AgentID, c.Key, c.RequestHash, c.Version).WillReturnResult(sqlmock.NewErrorResult(errors.New("rows failed")))
			}, want: "rows failed",
		},
		{
			name: "lost owner", setup: func(m sqlmock.Sqlmock, c ClaimToken) {
				m.ExpectBegin()
				m.ExpectExec(`SELECT set_config`).WithArgs(c.Principal.OrgID.String()).WillReturnResult(sqlmock.NewResult(0, 1))
				m.ExpectExec(`DELETE FROM ibex_core\.idempotency_ledger`).WithArgs(c.ID, c.Principal.OrgID, c.Principal.AgentID, c.Key, c.RequestHash, c.Version).WillReturnResult(sqlmock.NewResult(0, 0))
			}, want: ErrLedgerConflict.Error(),
		},
		{
			name: "commit", setup: func(m sqlmock.Sqlmock, c ClaimToken) {
				m.ExpectBegin()
				m.ExpectExec(`SELECT set_config`).WithArgs(c.Principal.OrgID.String()).WillReturnResult(sqlmock.NewResult(0, 1))
				m.ExpectExec(`DELETE FROM ibex_core\.idempotency_ledger`).WithArgs(c.ID, c.Principal.OrgID, c.Principal.AgentID, c.Key, c.RequestHash, c.Version).WillReturnResult(sqlmock.NewResult(0, 1))
				m.ExpectCommit().WillReturnError(errors.New("commit failed"))
			}, want: "commit failed",
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			db, mock, err := sqlmock.New()
			if err != nil {
				t.Fatal(err)
			}
			t.Cleanup(func() { _ = db.Close() })
			l, err := NewPostgresLedger(db, time.Minute)
			if err != nil {
				t.Fatal(err)
			}
			tc.setup(mock, claim)
			err = l.Release(ctx, claim)
			if err == nil || !strings.Contains(err.Error(), tc.want) {
				t.Fatalf("release error=%v want %q", err, tc.want)
			}
			if err := mock.ExpectationsWereMet(); err != nil {
				t.Fatal(err)
			}
		})
	}
}

func TestPostgresLedgerReleaseSuccess(t *testing.T) {
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = db.Close() })
	ledger, err := NewPostgresLedger(db, time.Minute)
	if err != nil {
		t.Fatal(err)
	}
	claim := releaseTestClaim()
	mock.ExpectBegin()
	mock.ExpectExec(`SELECT set_config`).WithArgs(claim.Principal.OrgID.String()).WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectExec(`DELETE FROM ibex_core\.idempotency_ledger`).WithArgs(claim.ID, claim.Principal.OrgID, claim.Principal.AgentID, claim.Key, claim.RequestHash, claim.Version).WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectCommit()
	if err := ledger.Release(context.Background(), claim); err != nil {
		t.Fatal(err)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestPostgresLedgerFinalizeRowsAffectedFailure(t *testing.T) {
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = db.Close() })
	ledger, err := NewPostgresLedger(db, time.Minute)
	if err != nil {
		t.Fatal(err)
	}
	claim := releaseTestClaim()
	mock.ExpectBegin()
	mock.ExpectExec(`SELECT set_config`).WithArgs(claim.Principal.OrgID.String()).WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectExec(`UPDATE ibex_core\.idempotency_ledger`).WillReturnResult(sqlmock.NewErrorResult(errors.New("rows failed")))
	if err := ledger.Finalize(context.Background(), claim, 200, []byte(`{"ok":true}`)); err == nil || !strings.Contains(err.Error(), "rows failed") {
		t.Fatalf("finalize error=%v", err)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}
