package repository

import (
	"database/sql"
	"errors"

	"github.com/Rick1330/ibex-harness/packages/metrics"
)

// ErrNilDB is returned when NewTokensRepository is constructed with a nil *sql.DB.
var ErrNilDB = errors.New("repository: nil db")

// NewTokensRepository constructs a TokensRepository. Returns ErrNilDB when db is nil.
func NewTokensRepository(db *sql.DB, obs metrics.QueryObserver) (*TokensRepository, error) {
	if db == nil {
		return nil, ErrNilDB
	}
	return &TokensRepository{db: db, obs: obs}, nil
}

// testFataler is satisfied by *testing.T and testing.TB without importing testing here.
type testFataler interface {
	Helper()
	Fatalf(format string, args ...any)
}

// RequireTokensRepository returns a TokensRepository or fails the test.
func RequireTokensRepository(t testFataler, db *sql.DB, obs metrics.QueryObserver) *TokensRepository {
	t.Helper()
	repo, err := NewTokensRepository(db, obs)
	if err != nil {
		t.Fatalf("NewTokensRepository: %v", err)
	}
	return repo
}
