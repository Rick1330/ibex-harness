package bootstrap

import (
	"context"
	"errors"
	"regexp"
	"strings"
	"testing"

	"github.com/DATA-DOG/go-sqlmock"
)

// loginColumns mirrors the column order of capabilityLoginSQL.
var loginColumns = []string{"current_user", "session_user", "current_super", "session_super"}

// loginIdentity is one connection identity as capabilityLoginSQL reads it back:
// the login the connection runs as, the session login behind it, and whether
// either of them is a superuser.
type loginIdentity struct {
	current      string
	session      string
	currentSuper bool
	sessionSuper bool
}

// row renders the identity as the result row capabilityLoginSQL returns.
func (id loginIdentity) row() *sqlmock.Rows {
	return sqlmock.NewRows(loginColumns).AddRow(id.current, id.session, id.currentSuper, id.sessionSuper)
}

func TestUnit_AssertProxyCapabilityLogin(t *testing.T) {
	t.Parallel()

	cases := []struct {
		name    string
		login   loginIdentity
		wantErr string
	}{
		{
			name:  "capability login passes",
			login: loginIdentity{current: runtimeCapabilityLogin, session: runtimeCapabilityLogin},
		},
		{
			name:    "owner login fails",
			login:   loginIdentity{current: ownerLogin, session: ownerLogin},
			wantErr: `connection login is "ibex", the owner login`,
		},
		{
			name:    "owner session behind a pinned capability role fails",
			login:   loginIdentity{current: runtimeCapabilityLogin, session: ownerLogin},
			wantErr: `connection login is "ibex", the owner login`,
		},
		{
			name:    "superuser current role fails",
			login:   loginIdentity{current: runtimeCapabilityLogin, session: runtimeCapabilityLogin, currentSuper: true},
			wantErr: "is a superuser",
		},
		{
			name:    "superuser session fails",
			login:   loginIdentity{current: runtimeCapabilityLogin, session: runtimeCapabilityLogin, sessionSuper: true},
			wantErr: "is a superuser",
		},
		{
			name:    "another capability login fails",
			login:   loginIdentity{current: "ibex_auth", session: "ibex_auth"},
			wantErr: `connection login is "ibex_auth", want the "ibex_runtime" capability login`,
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			err := proxyLoginCheck(t, tc.login)
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

func TestUnit_AssertProxyCapabilityLogin_QueryErrorFailsClosed(t *testing.T) {
	t.Parallel()

	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatalf("sqlmock: %v", err)
	}
	t.Cleanup(func() { _ = db.Close() })

	mock.ExpectQuery(regexp.QuoteMeta(capabilityLoginSQL)).WillReturnError(errors.New("connection reset"))

	err = assertProxyCapabilityLogin(context.Background(), db)
	if err == nil || !strings.Contains(err.Error(), "verify login role") {
		t.Fatalf("a failed check must fail closed, got %v", err)
	}
	if qerr := mock.ExpectationsWereMet(); qerr != nil {
		t.Fatalf("query expectations: %v", qerr)
	}
}

// proxyLoginCheck runs the assertion against a stubbed connection identity.
func proxyLoginCheck(t *testing.T, id loginIdentity) error {
	t.Helper()

	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatalf("sqlmock: %v", err)
	}
	t.Cleanup(func() { _ = db.Close() })

	mock.ExpectQuery(regexp.QuoteMeta(capabilityLoginSQL)).WillReturnRows(id.row())

	err = assertProxyCapabilityLogin(context.Background(), db)
	if qerr := mock.ExpectationsWereMet(); qerr != nil {
		t.Fatalf("query expectations: %v", qerr)
	}
	return err
}
