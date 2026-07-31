package service

import (
	"time"
)

type createTokenCase struct {
	name    string
	in      CreateTokenInput
	wantErr error
}

func createTokenCases(orgID, userID, agentID string, expires time.Time) []createTokenCase {
	return []createTokenCase{
		{name: "invalid empty org", in: CreateTokenInput{Name: "x"}, wantErr: ErrInvalidArgument},
		{name: "invalid empty name", in: CreateTokenInput{OrgID: orgID}, wantErr: ErrInvalidArgument},
		{
			name:    "invalid token type",
			in:      CreateTokenInput{OrgID: orgID, Name: "bad-type", TokenType: TokenType(99)},
			wantErr: ErrInvalidArgument,
		},
		{
			name: "happy path",
			in: CreateTokenInput{
				OrgID: orgID, Name: "ci-pat", Description: "desc", Permissions: 42,
				UserID: &userID, AgentID: &agentID, ExpiresAt: &expires, TokenType: TokenTypePAT,
			},
		},
	}
}
