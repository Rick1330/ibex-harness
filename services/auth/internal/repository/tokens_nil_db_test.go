package repository_test

import (
	"errors"
	"testing"

	"github.com/Rick1330/ibex-harness/services/auth/internal/repository"
)

func TestUnit_NewTokensRepository_NilDB(t *testing.T) {
	t.Parallel()
	repo, err := repository.NewTokensRepository(nil, nil)
	if err == nil {
		t.Fatal("expected error for nil db")
	}
	if repo != nil {
		t.Fatal("expected nil repo")
	}
	if got := err.Error(); got != "repository: nil db" {
		t.Fatalf("error: %q", got)
	}
	if errors.Is(err, repository.ErrNotFound) {
		t.Fatal("nil db must not be ErrNotFound")
	}
}
