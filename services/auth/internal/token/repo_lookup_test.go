package token_test

import (
	"context"
	"database/sql"
	"errors"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/services/auth/internal/repository"
	"github.com/Rick1330/ibex-harness/services/auth/internal/token"
)

type stubRepoLookup struct {
	row repository.TokenRow
	err error
}

func (s stubRepoLookup) FindActiveByPrefix(context.Context, string) (repository.TokenRow, error) {
	return s.row, s.err
}

func TestRepoLookup_FindActiveByPrefix(t *testing.T) {
	t.Parallel()
	agentID := "agent-1"
	userID := "user-1"
	expires := time.Date(2026, 7, 1, 0, 0, 0, 0, time.UTC)
	lookup, err := token.NewRepoLookup(stubRepoLookup{row: sampleRepoTokenRow(agentID, userID, expires)})
	if err != nil {
		t.Fatalf("NewRepoLookup: %v", err)
	}
	got, err := lookup.FindActiveByPrefix(context.Background(), "pfx")
	if err != nil {
		t.Fatalf("FindActiveByPrefix: %v", err)
	}
	want := token.Row{
		ID: "tid", OrgID: "oid", Hash: "h", Permissions: 3,
		AgentID: &agentID, UserID: &userID, ExpiresAt: &expires,
	}
	assertMappedRow(t, got, want)
}

func TestRepoLookup_FindActiveByPrefix_DelegatesError(t *testing.T) {
	t.Parallel()
	sentinel := errors.New("lookup failed")
	lookup, err := token.NewRepoLookup(stubRepoLookup{err: sentinel})
	if err != nil {
		t.Fatalf("NewRepoLookup: %v", err)
	}
	_, err = lookup.FindActiveByPrefix(context.Background(), "pfx")
	if !errors.Is(err, sentinel) {
		t.Fatalf("err=%v want %v", err, sentinel)
	}
}

func TestUnit_NewRepoLookup_RejectsNilInner(t *testing.T) {
	t.Parallel()
	_, err := token.NewRepoLookup(nil)
	if !errors.Is(err, token.ErrNilRepoLookupInner) {
		t.Fatalf("err=%v want %v", err, token.ErrNilRepoLookupInner)
	}
}

func TestUnit_RepoLookup_FindActiveByPrefix_NilInner(t *testing.T) {
	t.Parallel()
	_, err := (token.RepoLookup{}).FindActiveByPrefix(context.Background(), "pfx")
	if !errors.Is(err, token.ErrNilRepoLookupInner) {
		t.Fatalf("err=%v want %v", err, token.ErrNilRepoLookupInner)
	}
}

func sampleRepoTokenRow(agentID, userID string, expires time.Time) repository.TokenRow {
	return repository.TokenRow{
		ID: "tid", OrgID: "oid", Hash: "h", Permissions: 3,
		AgentID:   sql.NullString{String: agentID, Valid: true},
		UserID:    sql.NullString{String: userID, Valid: true},
		ExpiresAt: sql.NullTime{Time: expires, Valid: true},
	}
}

func assertMappedRow(t *testing.T, got, want token.Row) {
	t.Helper()
	assertRowCore(t, got, want)
	assertOptionalString(t, "agent", got.AgentID, want.AgentID)
	assertOptionalString(t, "user", got.UserID, want.UserID)
	assertOptionalTime(t, got.ExpiresAt, want.ExpiresAt)
}

func assertRowCore(t *testing.T, got, want token.Row) {
	t.Helper()
	if got.ID != want.ID {
		t.Fatalf("id=%q want %q", got.ID, want.ID)
	}
	if got.OrgID != want.OrgID {
		t.Fatalf("org_id=%q want %q", got.OrgID, want.OrgID)
	}
	if got.Hash != want.Hash {
		t.Fatalf("hash=%q want %q", got.Hash, want.Hash)
	}
	if got.Permissions != want.Permissions {
		t.Fatalf("permissions=%d want %d", got.Permissions, want.Permissions)
	}
}

func assertOptionalString(t *testing.T, label string, got, want *string) {
	t.Helper()
	if got == nil {
		if want != nil {
			t.Fatalf("%s: got nil want %q", label, *want)
		}
		return
	}
	if want == nil {
		t.Fatalf("%s: got %q want nil", label, *got)
	}
	if *got != *want {
		t.Fatalf("%s=%q want %q", label, *got, *want)
	}
}

func assertOptionalTime(t *testing.T, got, want *time.Time) {
	t.Helper()
	if got == nil {
		if want != nil {
			t.Fatalf("expires: got nil want %v", want)
		}
		return
	}
	if want == nil {
		t.Fatalf("expires: got %v want nil", got)
	}
	if !got.Equal(*want) {
		t.Fatalf("expires=%v want %v", got, want)
	}
}
