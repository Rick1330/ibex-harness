package sessionjwt_test

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/services/auth/internal/sessionjwt"
)

func TestLifecycleValidationRevocationAndStepUpReplay(t *testing.T) {
	issuer := mustIssuer(t, time.Minute, time.Hour, time.Minute)
	access, _, _, _, err := issuer.IssuePair(sessionjwt.IssuePairParams{
		Subject: "user-1", OrgID: "org-1", Permissions: 8, FamilyID: "family-1", SessionID: "session-1",
	})
	requireNoErr(t, err)
	accessClaims, err := issuer.ValidateAccess(context.Background(), sessionjwt.RawToken(access))
	requireNoErr(t, err)
	if accessClaims.SessionID != "session-1" {
		t.Fatalf("session binding mismatch: %q", accessClaims.SessionID)
	}
	step, _, err := issuer.IssueStepUp(sessionjwt.IssueStepUpParams{
		Subject: "user-1", OrgID: "org-1", Permissions: 8, SessionID: accessClaims.SessionID, Action: "legal_hold.manage",
	})
	requireNoErr(t, err)
	expect := sessionjwt.StepUpExpectations{Subject: "user-1", OrgID: "org-1", SessionID: accessClaims.SessionID, Action: "legal_hold.manage", RequiredPermission: 8}
	_, err = issuer.ConsumeStepUp(context.Background(), sessionjwt.RawToken(step), expect)
	requireNoErr(t, err)
	if _, err := issuer.ConsumeStepUp(context.Background(), sessionjwt.RawToken(step), expect); !errors.Is(err, sessionjwt.ErrInvalidToken) {
		t.Fatalf("step-up replay accepted: %v", err)
	}

	stepAfterLogout, _, err := issuer.IssueStepUp(sessionjwt.IssueStepUpParams{
		Subject: "user-1", OrgID: "org-1", Permissions: 8, SessionID: accessClaims.SessionID, Action: "legal_hold.manage",
	})
	requireNoErr(t, err)
	requireNoErr(t, issuer.RevokeSession(context.Background(), accessClaims.SessionID, "family-1", accessClaims.JTI))
	if _, err := issuer.ValidateAccess(context.Background(), sessionjwt.RawToken(access)); !errors.Is(err, sessionjwt.ErrInvalidToken) {
		t.Fatalf("revoked access accepted: %v", err)
	}
	if _, err := issuer.ConsumeStepUp(context.Background(), sessionjwt.RawToken(stepAfterLogout), expect); !errors.Is(err, sessionjwt.ErrInvalidToken) {
		t.Fatalf("step-up after logout accepted: %v", err)
	}
}
