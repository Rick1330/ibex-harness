package token

import (
	"context"
	"errors"

	"github.com/Rick1330/ibex-harness/services/auth/internal/repository"
)

// ErrNilRepoLookupInner indicates a RepoLookup was built without a backing store.
var ErrNilRepoLookupInner = errors.New("token: nil RepoLookup inner")

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
		return RepoLookup{}, ErrNilRepoLookupInner
	}
	return RepoLookup{inner: inner}, nil
}

// FindActiveByPrefix implements the Validator lookup port.
func (l RepoLookup) FindActiveByPrefix(ctx context.Context, prefix string) (Row, error) {
	if l.inner == nil {
		return Row{}, ErrNilRepoLookupInner
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
