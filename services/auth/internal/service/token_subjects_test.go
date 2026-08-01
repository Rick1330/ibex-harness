package service

import (
	"context"
	"errors"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/logger"
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

func TestUnit_CreateToken_SubjectOrgBind(t *testing.T) {
	t.Parallel()
	orgID := uuid.NewString()
	sameAgent := uuid.NewString()
	sameUser := uuid.NewString()
	foreignAgent := uuid.NewString()
	foreignUser := uuid.NewString()

	cases := []struct {
		name    string
		in      CreateTokenInput
		lookup  tokenSubjectLookup
		wantErr error
	}{
		{
			name: "no_subjects_ok_without_binds",
			in:   CreateTokenInput{OrgID: orgID, Name: "plain", TokenType: TokenTypePAT},
		},
		{
			name: "nil_lookup_rejects_agent_bind",
			in: CreateTokenInput{
				OrgID: orgID, Name: "a", TokenType: TokenTypePAT, AgentID: &sameAgent,
			},
			wantErr: ErrTokenSubjectForbidden,
		},
		{
			name: "cross_org_agent_forbidden",
			in: CreateTokenInput{
				OrgID: orgID, Name: "a", TokenType: TokenTypePAT, AgentID: &foreignAgent,
			},
			lookup:  scriptedSubjects{agentOK: false},
			wantErr: ErrTokenSubjectForbidden,
		},
		{
			name: "cross_org_user_forbidden",
			in: CreateTokenInput{
				OrgID: orgID, Name: "u", TokenType: TokenTypePAT, UserID: &foreignUser,
			},
			lookup:  scriptedSubjects{userOK: false},
			wantErr: ErrTokenSubjectForbidden,
		},
		{
			name: "same_org_agent_and_user_ok",
			in: CreateTokenInput{
				OrgID: orgID, Name: "ok", TokenType: TokenTypePAT,
				AgentID: &sameAgent, UserID: &sameUser,
			},
			lookup: scriptedSubjects{agentOK: true, userOK: true},
		},
		{
			name: "invalid_agent_uuid",
			in: CreateTokenInput{
				OrgID: orgID, Name: "bad", TokenType: TokenTypePAT,
				AgentID: strPtr("not-a-uuid"),
			},
			lookup:  allowAllSubjects{},
			wantErr: ErrInvalidArgument,
		},
		{
			name: "lookup_error_wrapped",
			in: CreateTokenInput{
				OrgID: orgID, Name: "err", TokenType: TokenTypePAT, AgentID: &sameAgent,
			},
			lookup:  scriptedSubjects{err: errors.New("db down")},
			wantErr: ErrTokenSubjectLookup,
		},
	}

	for _, tc := range cases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			repo := newMemTokenRepo()
			opts := []TokenServiceOption{}
			if tc.lookup != nil {
				opts = append(opts, WithSubjectLookup(tc.lookup))
			}
			svc := NewTokenService(repo, token.DefaultArgon2Params(), logger.Discard("auth"), nil, opts...)
			_, err := svc.CreateToken(context.Background(), tc.in)
			if tc.wantErr != nil {
				if !errors.Is(err, tc.wantErr) {
					t.Fatalf("err=%v want %v", err, tc.wantErr)
				}
				return
			}
			if err != nil {
				t.Fatalf("CreateToken: %v", err)
			}
		})
	}
}

func strPtr(s string) *string { return &s }
