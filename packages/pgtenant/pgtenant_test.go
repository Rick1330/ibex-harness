package pgtenant_test

import (
	"context"
	"database/sql"
	"errors"
	"strings"
	"testing"

	"github.com/DATA-DOG/go-sqlmock"
	"github.com/Rick1330/ibex-harness/packages/pgtenant"
	"github.com/google/uuid"
	"github.com/lib/pq"
)

// The two statements PinOrg must issue, matched strictly so the pin cannot
// regress to a session-level SET or to a GUC written before the role.
const (
	roleStatement = `^SET LOCAL ROLE ibex_app$`
	gucStatement  = `^SELECT set_config\('app\.current_org_id', \$1, true\)$`
)

// deniedRole is the error Postgres returns for a role the session may not
// assume. lib/pq renders it as `pq: <message> (42501)`, so the SQLSTATE is
// visible in the rendered message as well as through errors.As.
func deniedRole() *pq.Error {
	return &pq.Error{Code: "42501", Message: `permission denied to set role "ibex_app"`}
}

func openTx(t *testing.T) (*sql.DB, sqlmock.Sqlmock, *sql.Tx) {
	t.Helper()
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatalf("sqlmock: %v", err)
	}
	t.Cleanup(func() { _ = db.Close() })
	mock.ExpectBegin()
	tx, err := db.BeginTx(context.Background(), nil)
	if err != nil {
		t.Fatalf("begin: %v", err)
	}
	return db, mock, tx
}

// TestPinOrg_IssuesRoleThenTransactionLocalGUC is the ordering control: the
// role is assumed before the selector is written, and the selector is written
// transaction-locally (is_local = true) so a pooled connection cannot carry it
// into the next borrower.
func TestPinOrg_IssuesRoleThenTransactionLocalGUC(t *testing.T) {
	_, mock, tx := openTx(t)
	org := uuid.New()

	mock.ExpectExec(roleStatement).WillReturnResult(sqlmock.NewResult(0, 0))
	mock.ExpectExec(gucStatement).WithArgs(org.String()).WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectCommit()

	if err := pgtenant.PinOrg(context.Background(), tx, org); err != nil {
		t.Fatalf("PinOrg: %v", err)
	}
	if err := tx.Commit(); err != nil {
		t.Fatalf("commit: %v", err)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatalf("statement sequence: %v", err)
	}
}

// TestPinOrg_RoleDenialSurfaces42501 proves a capability login that may not
// assume ibex_app is reported, not swallowed, and that the pin stops there: the
// GUC statement is never issued, because setting it would leave the transaction
// looking scoped while running as the login.
func TestPinOrg_RoleDenialSurfaces42501(t *testing.T) {
	expectPinDenied(t, "SET LOCAL ROLE", func(mock sqlmock.Sqlmock, _ uuid.UUID) {
		mock.ExpectExec(roleStatement).WillReturnError(deniedRole())
	})
}

// TestPinOrg_GUCDenialSurfaces42501 covers the second statement: a role that
// was assumed but cannot read the selector must fail the pin, not continue with
// an unset org.
func TestPinOrg_GUCDenialSurfaces42501(t *testing.T) {
	expectPinDenied(t, "set_config", func(mock sqlmock.Sqlmock, org uuid.UUID) {
		mock.ExpectExec(roleStatement).WillReturnResult(sqlmock.NewResult(0, 0))
		mock.ExpectExec(gucStatement).WithArgs(org.String()).WillReturnError(deniedRole())
	})
}

// expectPinDenied runs one pin whose statement is denied: expect queues the
// statements up to and including the denial, and the pin must surface 42501
// rather than continue as an unscoped transaction.
func expectPinDenied(t *testing.T, statement string, expect func(sqlmock.Sqlmock, uuid.UUID)) {
	t.Helper()
	_, mock, tx := openTx(t)
	org := uuid.New()
	expect(mock, org)

	err := pgtenant.PinOrg(context.Background(), tx, org)
	if err == nil {
		t.Fatalf("PinOrg accepted a denied %s", statement)
	}
	assertPinDenied(t, err)
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatalf("statement sequence: %v", err)
	}
}

// TestPinOrg_TransportErrorIsWrappedNotSwallowed keeps the wrapper honest for
// the non-SQLSTATE case: a cancelled or dead connection must still be
// inspectable by the caller.
func TestPinOrg_TransportErrorIsWrappedNotSwallowed(t *testing.T) {
	_, mock, tx := openTx(t)

	mock.ExpectExec(roleStatement).WillReturnError(sql.ErrConnDone)

	err := pgtenant.PinOrg(context.Background(), tx, uuid.New())
	if !errors.Is(err, sql.ErrConnDone) {
		t.Fatalf("error=%v want it to wrap sql.ErrConnDone", err)
	}
	if !strings.Contains(err.Error(), "pgtenant: pin role") {
		t.Fatalf("error=%q missing pgtenant: pin role prefix", err)
	}
}

// assertPinDenied checks both halves of "not swallowed": the SQLSTATE survives
// the wrap for errors.As, and it is visible in the rendered message an operator
// greps for.
func assertPinDenied(t *testing.T, err error) {
	t.Helper()
	if !strings.Contains(err.Error(), "pgtenant: pin role") {
		t.Fatalf("error=%q missing pgtenant: pin role prefix", err)
	}
	if !strings.Contains(err.Error(), "42501") {
		t.Fatalf("error=%q does not mention 42501", err)
	}
	var pqErr *pq.Error
	if !errors.As(err, &pqErr) {
		t.Fatalf("error=%v does not wrap *pq.Error", err)
	}
	if pqErr.Code != "42501" {
		t.Fatalf("sqlstate=%s want 42501", pqErr.Code)
	}
}
