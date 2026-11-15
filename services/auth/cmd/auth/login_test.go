package main

import (
	"context"
	"database/sql"
	"errors"
	"regexp"
	"strings"
	"testing"

	"github.com/DATA-DOG/go-sqlmock"
)

// loginColumns mirrors the column order of capabilityLoginSQL.
var loginColumns = []string{"current_user", "session_user", "current_super", "session_super"}

func TestUnit_AssertAuthCapabilityLogin(t *testing.T) {
	t.Parallel()

	cases := []struct {
		name         string
		current      string
		session      string
		currentSuper bool
		sessionSuper bool
		wantErr      string
	}{
		{
			name:    "capability login passes",
			current: authCapabilityLogin, session: authCapabilityLogin,
		},
		{
			name:    "owner login fails",
			current: ownerLogin, session: ownerLogin,
			wantErr: `connection login is "ibex", the owner login`,
		},
		{
			name:    "owner session behind a pinned capability role fails",
			current: authCapabilityLogin, session: ownerLogin,
			wantErr: `connection login is "ibex", the owner login`,
		},
		{
			name:    "superuser current role fails",
			current: authCapabilityLogin, session: authCapabilityLogin, currentSuper: true,
			wantErr: "is a superuser",
		},
		{
			name:    "superuser session fails",
			current: authCapabilityLogin, session: authCapabilityLogin, sessionSuper: true,
			wantErr: "is a superuser",
		},
		{
			name:    "another capability login fails",
			current: "ibex_runtime", session: "ibex_runtime",
			wantErr: `connection login is "ibex_runtime", want the "ibex_auth" capability login`,
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			err := authLoginCheck(t, authLoginIdentity{
				current: tc.current, session: tc.session,
				currentSuper: tc.currentSuper, sessionSuper: tc.sessionSuper,
			})
			if tc.wantErr == "" {
				if err != nil {
					t.Fatalf("want pass, got %v", err)
				}
				return
			}
			if err == nil || !strings.Contains(err.Error(), tc.wantErr) {
				t.Fatalf("want error containing %q, got %v", tc.wantErr, err)
			}
		})
	}
}

func TestUnit_AssertAuthCapabilityLogin_QueryErrorFailsClosed(t *testing.T) {
	t.Parallel()

	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatalf("sqlmock: %v", err)
	}
	t.Cleanup(func() { _ = db.Close() })

	mock.ExpectQuery(regexp.QuoteMeta(capabilityLoginSQL)).WillReturnError(errors.New("connection reset"))

	err = assertAuthCapabilityLogin(context.Background(), db)
	if err == nil || !strings.Contains(err.Error(), "verify login role") {
		t.Fatalf("a failed check must fail closed, got %v", err)
	}
	if qerr := mock.ExpectationsWereMet(); qerr != nil {
		t.Fatalf("query expectations: %v", qerr)
	}
}

// stubAuthLoginVerification replaces the startup login assertion for tests that
// exercise startup orchestration without a database. It must not be used from a
// parallel test.
func stubAuthLoginVerification(t *testing.T) {
	t.Helper()
	restore := verifyAuthDBLogin
	verifyAuthDBLogin = func(context.Context, *sql.DB) error { return nil }
	t.Cleanup(func() { verifyAuthDBLogin = restore })
}

// authLoginIdentity is the four values the startup assertion inspects.
// Grouping them keeps the helper's signature small and makes each case a
// single value rather than four positional booleans.
type authLoginIdentity struct {
	current      string
	session      string
	currentSuper bool
	sessionSuper bool
}

// authLoginCheck runs the assertion against a stubbed connection identity.
func authLoginCheck(t *testing.T, id authLoginIdentity) error {
	t.Helper()

	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatalf("sqlmock: %v", err)
	}
	t.Cleanup(func() { _ = db.Close() })

	mock.ExpectQuery(regexp.QuoteMeta(capabilityLoginSQL)).
		WillReturnRows(sqlmock.NewRows(loginColumns).
			AddRow(id.current, id.session, id.currentSuper, id.sessionSuper))

	err = assertAuthCapabilityLogin(context.Background(), db)
	if qerr := mock.ExpectationsWereMet(); qerr != nil {
		t.Fatalf("query expectations: %v", qerr)
	}
	return err
}
