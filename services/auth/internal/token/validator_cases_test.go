package token_test

import (
	"database/sql"
	"errors"

	"github.com/Rick1330/ibex-harness/services/auth/internal/token"
)

type validatorCase struct {
	name    string
	token   string
	lookup  *fakeLookup
	wantErr error
	expect  string
}

type validatorFixture struct {
	bearer, hash, agentID, userID string
	row                           token.Row
}

func validatorCases(f validatorFixture) []validatorCase {
	return []validatorCase{
		{name: "malformed token", token: "not-a-token", lookup: &fakeLookup{}, wantErr: token.ErrUnauthenticated},
		{name: "not found", token: f.bearer, lookup: &fakeLookup{err: sql.ErrNoRows}, wantErr: token.ErrUnauthenticated},
		{name: "wrong hash", token: f.bearer, lookup: &fakeLookup{row: token.Row{Hash: "wrong", OrgID: "org"}}, wantErr: token.ErrUnauthenticated},
		{name: "db error", token: f.bearer, lookup: &fakeLookup{err: errors.New("db down")}, expect: "db error"},
		{name: "ok with optional fields", token: f.bearer, lookup: &fakeLookup{row: f.row}, expect: "ok"},
	}
}
