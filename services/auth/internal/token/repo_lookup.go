package token

import (
	"context"
	"fmt"

	"github.com/Rick1330/ibex-harness/services/auth/internal/repository"
)

// repoActiveLookup is the persistence port adapted into domain Row.
type repoActiveLookup interface {
	FindActiveByPrefix(ctx context.Context, prefix string) (repository.TokenRow, error)
}

// RepoLookup adapts repository.TokenRow into token.Row for Validator.
type RepoLookup struct {
	inner repoActiveLookup
}

// NewRepoLookup returns a Validator lookup adapter over a repository store.
// inner must be non-nil.
func NewRepoLookup(inner repoActiveLookup) (RepoLookup, error) {
	if inner == nil {
		return RepoLookup{}, fmt.Errorf("token: nil RepoLookup inner")
	}
	return RepoLookup{inner: inner}, nil
}

// FindActiveByPrefix implements the Validator lookup port.
func (l RepoLookup) FindActiveByPrefix(ctx context.Context, prefix string) (Row, error) {
	if l.inner == nil {
		return Row{}, fmt.Errorf("token: nil RepoLookup inner")
	}
	row, err := l.inner.FindActiveByPrefix(ctx, prefix)
	if err != nil {
		return Row{}, err
	}
	return rowFromRepository(row), nil
}

func rowFromRepository(row repository.TokenRow) Row {
	out := Row{
		ID: row.ID, OrgID: row.OrgID, Permissions: row.Permissions, Hash: row.Hash,
	}
	if row.UserID.Valid {
		s := row.UserID.String
		out.UserID = &s
	}
	if row.AgentID.Valid {
		s := row.AgentID.String
		out.AgentID = &s
	}
	if row.ExpiresAt.Valid {
		t := row.ExpiresAt.Time
		out.ExpiresAt = &t
	}
	return out
}
