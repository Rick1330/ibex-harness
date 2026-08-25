package service

import (
	"context"
	"errors"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/services/auth/internal/repository"
	"github.com/Rick1330/ibex-harness/services/auth/internal/token"
	"github.com/google/uuid"
)

type scriptedSubjects struct {
	agentOK bool
	userOK  bool
	err     error
}

func (s scriptedSubjects) AgentBelongsToOrg(context.Context, uuid.UUID, uuid.UUID) (bool, error) {
	return s.agentOK, s.err
}

func (s scriptedSubjects) UserBelongsToOrg(context.Context, uuid.UUID, uuid.UUID) (bool, error) {
	return s.userOK, s.err
}

type scriptedAgentLookup struct {
	rec *repository.AgentRecord
	err error
}

func (s scriptedAgentLookup) GetByIDAndOrg(context.Context, uuid.UUID, uuid.UUID) (*repository.AgentRecord, error) {
	return s.rec, s.err
}

type scriptedUserFinder struct {
	rec *repository.UserRecord
	err error
}

func (s scriptedUserFinder) Find(context.Context, uuid.UUID, uuid.UUID) (*repository.UserRecord, error) {
	return s.rec, s.err
}

type valueAgentLookup struct{}

func (valueAgentLookup) GetByIDAndOrg(context.Context, uuid.UUID, uuid.UUID) (*repository.AgentRecord, error) {
	return &repository.AgentRecord{ID: "a"}, nil
}

type subjectBindIDs struct {
	org, sameAgent, sameUser, foreignAgent, foreignUser string
}

func subjectBindCases(ids subjectBindIDs) []struct {
	name    string
	in      CreateTokenInput
	lookup  tokenSubjectLookup
	wantErr error
} {
	return []struct {
		name    string
		in      CreateTokenInput
		lookup  tokenSubjectLookup
		wantErr error
	}{
		{name: "no_subjects_ok_without_binds", in: CreateTokenInput{OrgID: ids.org, Name: "plain", TokenType: TokenTypePAT}},
		{
			name: "nil_lookup_unavailable",
			in: CreateTokenInput{
				OrgID: ids.org, Name: "a", TokenType: TokenTypePAT, AgentID: &ids.sameAgent,
			},
			wantErr: ErrTokenSubjectUnavailable,
		},
		{
			name: "cross_org_agent_forbidden",
			in: CreateTokenInput{
				OrgID: ids.org, Name: "a", TokenType: TokenTypePAT, AgentID: &ids.foreignAgent,
			},
			lookup: scriptedSubjects{agentOK: false}, wantErr: ErrTokenSubjectForbidden,
		},
		{
			name: "cross_org_user_forbidden",
			in: CreateTokenInput{
				OrgID: ids.org, Name: "u", TokenType: TokenTypePAT, UserID: &ids.foreignUser,
			},
			lookup: scriptedSubjects{userOK: false}, wantErr: ErrTokenSubjectForbidden,
		},
		{
			name: "same_org_agent_and_user_ok",
			in: CreateTokenInput{
				OrgID: ids.org, Name: "ok", TokenType: TokenTypePAT,
				AgentID: &ids.sameAgent, UserID: &ids.sameUser,
			},
			lookup: scriptedSubjects{agentOK: true, userOK: true},
		},
		{
			name: "invalid_agent_uuid",
			in: CreateTokenInput{
				OrgID: ids.org, Name: "bad", TokenType: TokenTypePAT, AgentID: strPtr("not-a-uuid"),
			},
			lookup: scriptedSubjects{}, wantErr: ErrInvalidArgument,
		},
		{
			name: "empty_user_id",
			in: CreateTokenInput{
				OrgID: ids.org, Name: "empty", TokenType: TokenTypePAT, UserID: strPtr(""),
			},
			lookup: scriptedSubjects{userOK: true}, wantErr: ErrInvalidArgument,
		},
		{
			name: "invalid_org_id_with_bind",
			in: CreateTokenInput{
				OrgID: "not-org", Name: "bad-org", TokenType: TokenTypePAT, AgentID: &ids.sameAgent,
			},
			lookup: scriptedSubjects{agentOK: true}, wantErr: ErrInvalidArgument,
		},
		{
			name: "lookup_error_wrapped",
			in: CreateTokenInput{
				OrgID: ids.org, Name: "err", TokenType: TokenTypePAT, AgentID: &ids.sameAgent,
			},
			lookup: scriptedSubjects{err: errors.New("db down")}, wantErr: ErrTokenSubjectLookup,
		},
	}
}

func TestUnit_CreateToken_SubjectOrgBind(t *testing.T) {
	t.Parallel()
	cases := subjectBindCases(subjectBindIDs{
		org: uuid.NewString(), sameAgent: uuid.NewString(), sameUser: uuid.NewString(),
		foreignAgent: uuid.NewString(), foreignUser: uuid.NewString(),
	})
	for _, tc := range cases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			runSubjectBindCase(t, tc.in, tc.lookup, tc.wantErr)
		})
	}
}

func runSubjectBindCase(t *testing.T, in CreateTokenInput, lookup tokenSubjectLookup, wantErr error) {
	t.Helper()
	svc := NewTokenService(newMemTokenRepo(), token.DefaultArgon2Params(), logger.Discard("auth"), nil)
	if lookup != nil {
		svc = svc.WithSubjectLookup(lookup)
	}
	_, err := svc.CreateToken(context.Background(), in)
	assertSubjectBindErr(t, err, wantErr)
}

func assertSubjectBindErr(t *testing.T, err, wantErr error) {
	t.Helper()
	if wantErr != nil {
		if !errors.Is(err, wantErr) {
			t.Fatalf("err=%v want %v", err, wantErr)
		}
		return
	}
	if err != nil {
		t.Fatalf("CreateToken: %v", err)
	}
}

func TestUnit_NewRepoTokenSubjects_RejectsNil(t *testing.T) {
	t.Parallel()
	users := UsersFinder(&repository.UsersRepository{})
	if _, err := NewRepoTokenSubjects(nil, users); err == nil {
		t.Fatal("expected nil agents error")
	}
	if _, err := NewRepoTokenSubjects(&repository.AgentsRepository{}, nil); err == nil {
		t.Fatal("expected nil users error")
	}
	if _, err := NewRepoTokenSubjects(&repository.AgentsRepository{}, UsersFinder(nil)); err == nil {
		t.Fatal("expected UsersFinder(nil) error")
	}
	var typedNilAgents *repository.AgentsRepository
	if _, err := NewRepoTokenSubjects(typedNilAgents, users); err == nil {
		t.Fatal("expected typed-nil agents error")
	}
	var typedNilUsers *usersFindAdapter
	if _, err := NewRepoTokenSubjects(&repository.AgentsRepository{}, typedNilUsers); err == nil {
		t.Fatal("expected typed-nil users error")
	}
}

func TestUnit_RepoTokenSubjects_BelongsHit(t *testing.T) {
	t.Parallel()
	agentID := uuid.New()
	userID := uuid.New()
	orgID := uuid.New()
	subjects := mustRepoSubjects(t,
		scriptedAgentLookup{rec: &repository.AgentRecord{ID: agentID.String()}},
		scriptedUserFinder{rec: &repository.UserRecord{ID: userID.String()}},
	)
	ok, err := subjects.AgentBelongsToOrg(context.Background(), agentID, orgID)
	assertBelongsOK(t, ok, err)
	ok, err = subjects.UserBelongsToOrg(context.Background(), userID, orgID)
	assertBelongsOK(t, ok, err)
}

func TestUnit_RepoTokenSubjects_BelongsMiss(t *testing.T) {
	t.Parallel()
	subjects := mustRepoSubjects(t, scriptedAgentLookup{}, scriptedUserFinder{})
	id := uuid.New()
	org := uuid.New()
	ok, err := subjects.AgentBelongsToOrg(context.Background(), id, org)
	assertBelongsMiss(t, ok, err)
	ok, err = subjects.UserBelongsToOrg(context.Background(), id, org)
	assertBelongsMiss(t, ok, err)
}

func mustRepoSubjects(t *testing.T, agents getByIDAndOrger, users userOrgFinder) tokenSubjectLookup {
	t.Helper()
	subjects, err := NewRepoTokenSubjects(agents, users)
	if err != nil {
		t.Fatalf("NewRepoTokenSubjects: %v", err)
	}
	return subjects
}

func assertBelongsOK(t *testing.T, ok bool, err error) {
	t.Helper()
	if err != nil {
		t.Fatalf("belongs err: %v", err)
	}
	if !ok {
		t.Fatal("expected belongs=true")
	}
}

func assertBelongsMiss(t *testing.T, ok bool, err error) {
	t.Helper()
	if err != nil {
		t.Fatalf("belongs err: %v", err)
	}
	if ok {
		t.Fatal("expected belongs=false")
	}
}

func TestUnit_RepoTokenSubjects_LookupErrors(t *testing.T) {
	t.Parallel()
	boom := errors.New("db")
	subjects, err := NewRepoTokenSubjects(
		scriptedAgentLookup{err: boom},
		scriptedUserFinder{err: boom},
	)
	if err != nil {
		t.Fatalf("NewRepoTokenSubjects: %v", err)
	}
	if _, err := subjects.AgentBelongsToOrg(context.Background(), uuid.New(), uuid.New()); err == nil {
		t.Fatal("expected agent lookup error")
	}
	if _, err := subjects.UserBelongsToOrg(context.Background(), uuid.New(), uuid.New()); err == nil {
		t.Fatal("expected user lookup error")
	}
}

func TestUnit_NewRepoTokenSubjects_ValueReceiverDep(t *testing.T) {
	t.Parallel()
	subjects, err := NewRepoTokenSubjects(valueAgentLookup{}, scriptedUserFinder{
		rec: &repository.UserRecord{ID: "u"},
	})
	if err != nil {
		t.Fatalf("value agent dep: %v", err)
	}
	ok, err := subjects.AgentBelongsToOrg(context.Background(), uuid.New(), uuid.New())
	if err != nil || !ok {
		t.Fatalf("value agent belongs: ok=%v err=%v", ok, err)
	}
}

func TestUnit_UsersFinder_WrapsRepo(t *testing.T) {
	t.Parallel()
	repo := &repository.UsersRepository{}
	finder := UsersFinder(repo)
	adapter, ok := finder.(usersFindAdapter)
	if !ok {
		t.Fatalf("type=%T", finder)
	}
	if adapter.repo != repo {
		t.Fatal("adapter repo mismatch")
	}
}

func TestUnit_TokenBindResourceID(t *testing.T) {
	t.Parallel()
	agent := "agent-1"
	user := "user-1"
	cases := []struct {
		name string
		in   CreateTokenInput
		want string
	}{
		{name: "empty", want: ""},
		{name: "agent_only", in: CreateTokenInput{AgentID: &agent}, want: "agent-1"},
		{name: "user_only", in: CreateTokenInput{UserID: &user}, want: "user-1"},
		{name: "both", in: CreateTokenInput{AgentID: &agent, UserID: &user}, want: "agent:agent-1,user:user-1"},
	}
	for _, tc := range cases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			if got := TokenBindResourceID(tc.in); got != tc.want {
				t.Fatalf("got %q want %q", got, tc.want)
			}
		})
	}
}

func strPtr(s string) *string { return &s }
