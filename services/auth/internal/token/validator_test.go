package token_test

import (
	"context"
	"errors"
	"testing"
	"time"

	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"github.com/Rick1330/ibex-harness/services/auth/internal/token"
	"github.com/google/uuid"
)

func assertValidatorError(t *testing.T, err, want error) {
	t.Helper()
	if !errors.Is(err, want) {
		t.Fatalf("err: got %v want %v", err, want)
	}
}

type validatorRun struct {
	argon2          token.Argon2Params
	tc              validatorCase
	agentID, userID string
}

func assertValidatorResponse(t *testing.T, resp *authv1.ValidateTokenResponse, agentID, userID string) {
	t.Helper()
	if resp.GetOrgId() == "" {
		t.Fatalf("resp: %+v", resp)
	}
	if resp.GetPermissions() != 42 {
		t.Fatalf("perms: %d", resp.GetPermissions())
	}
	if resp.GetAgentId() != agentID {
		t.Fatal("agent id missing")
	}
	if resp.GetUserId() != userID {
		t.Fatal("user id missing")
	}
}

func runValidatorCase(t *testing.T, run validatorRun) {
	t.Helper()
	v, err := token.NewValidator(run.tc.lookup, run.argon2)
	if err != nil {
		t.Fatalf("NewValidator: %v", err)
	}
	resp, err := v.Validate(context.Background(), run.tc.token)
	if run.tc.wantErr != nil {
		assertValidatorError(t, err, run.tc.wantErr)
		return
	}
	if run.tc.expect == "db error" {
		if err == nil {
			t.Fatal("expected error")
		}
		return
	}
	if err != nil {
		t.Fatalf("Validate: %v", err)
	}
	assertValidatorResponse(t, resp, run.agentID, run.userID)
}

type fakeLookup struct {
	row token.Row
	err error
}

func (f *fakeLookup) FindActiveByPrefix(ctx context.Context, _ string) (token.Row, error) {
	if f.err != nil {
		return token.Row{}, f.err
	}
	return f.row, nil
}

func TestValidator_Validate(t *testing.T) {
	t.Parallel()
	argon2 := token.TestArgon2Params()
	tokenID := uuid.New()
	bearer := "ibex_pat_" + tokenID.String() + "_secret"
	hash, err := token.HashForTest(bearer, argon2)
	if err != nil {
		t.Fatal(err)
	}
	otherHash, err := token.HashForTest(bearer+"_other", argon2)
	if err != nil {
		t.Fatal(err)
	}
	agentID := uuid.NewString()
	userID := uuid.NewString()
	expires := time.Now().UTC().Add(time.Hour)
	row := token.Row{
		ID: tokenID.String(), OrgID: uuid.NewString(), Hash: hash, Permissions: 42,
		AgentID: &agentID, UserID: &userID, ExpiresAt: &expires,
	}
	for _, tc := range validatorCases(validatorFixture{
		bearer: bearer, hash: hash, otherHash: otherHash, agentID: agentID, userID: userID, row: row,
	}) {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			runValidatorCase(t, validatorRun{argon2: argon2, tc: tc, agentID: agentID, userID: userID})
		})
	}
}
