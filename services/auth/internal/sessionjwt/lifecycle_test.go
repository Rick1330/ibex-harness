package sessionjwt_test

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/services/auth/internal/sessionjwt"
)

func TestValidateAccessAndRefreshProofsBindSessionFamily(t *testing.T) {
	issuer := mustIssuer(t, time.Minute, time.Hour, time.Minute)
	access, refresh, _, _, err := issuer.IssuePair(sessionjwt.IssuePairParams{
		Subject: "user-1", OrgID: "org-1", Permissions: 8, FamilyID: "family-1", SessionID: "session-1",
	})
	requireNoErr(t, err)
	accessClaims, err := issuer.ValidateAccess(context.Background(), sessionjwt.RawToken(access))
	requireNoErr(t, err)
	if accessClaims.SessionID != "session-1" || accessClaims.FamilyID != "family-1" {
		t.Fatalf("access session/family binding mismatch: %+v", accessClaims)
	}
	refreshClaims, err := issuer.VerifyRefreshProof(sessionjwt.RefreshToken(refresh))
	requireNoErr(t, err)
	if refreshClaims.SessionID != accessClaims.SessionID || refreshClaims.FamilyID != accessClaims.FamilyID {
		t.Fatalf("access/refresh proof mismatch: access=%+v refresh=%+v", accessClaims, refreshClaims)
	}
	if _, err := issuer.VerifyAccessProof(sessionjwt.RawToken(access)); err != nil {
		t.Fatalf("valid access logout proof rejected: %v", err)
	}
}

func TestStepUpConsumeRejectsReplay(t *testing.T) {
	issuer := mustIssuer(t, time.Minute, time.Hour, time.Minute)
	access, _, _, _, err := issuer.IssuePair(sessionjwt.IssuePairParams{
		Subject: "user-1", OrgID: "org-1", Permissions: 8, FamilyID: "family-1", SessionID: "session-1",
	})
	requireNoErr(t, err)
	accessClaims, err := issuer.ValidateAccess(context.Background(), sessionjwt.RawToken(access))
	requireNoErr(t, err)
	step, _, err := issuer.IssueStepUp(sessionjwt.IssueStepUpParams{
		Subject: "user-1", OrgID: "org-1", Permissions: 8, SessionID: accessClaims.SessionID, Action: "legal_hold.manage",
	})
	requireNoErr(t, err)
	expect := sessionjwt.StepUpExpectations{
		Subject: "user-1", OrgID: "org-1", SessionID: accessClaims.SessionID,
		Action: "legal_hold.manage", RequiredPermission: 8,
	}
	_, err = issuer.ConsumeStepUp(context.Background(), sessionjwt.RawToken(step), expect)
	requireNoErr(t, err)
	if _, err := issuer.ConsumeStepUp(context.Background(), sessionjwt.RawToken(step), expect); !errors.Is(err, sessionjwt.ErrInvalidToken) {
		t.Fatalf("step-up replay accepted: %v", err)
	}
}

func TestRevokeSessionInvalidatesAccessStepUpAndRefresh(t *testing.T) {
	issuer := mustIssuer(t, time.Minute, time.Hour, time.Minute)
	access, refresh, _, _, err := issuer.IssuePair(sessionjwt.IssuePairParams{
		Subject: "user-1", OrgID: "org-1", Permissions: 8, FamilyID: "family-1", SessionID: "session-1",
	})
	requireNoErr(t, err)
	accessClaims, err := issuer.ValidateAccess(context.Background(), sessionjwt.RawToken(access))
	requireNoErr(t, err)
	expect := sessionjwt.StepUpExpectations{
		Subject: "user-1", OrgID: "org-1", SessionID: accessClaims.SessionID,
		Action: "legal_hold.manage", RequiredPermission: 8,
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
	if _, err := issuer.VerifyAccessProof(sessionjwt.RawToken(access)); err != nil {
		t.Fatalf("revoked access must remain verifiable as an idempotent logout proof: %v", err)
	}
	if _, _, _, _, err := issuer.RefreshPair(context.Background(), sessionjwt.RefreshToken(refresh)); !errors.Is(err, sessionjwt.ErrInvalidToken) {
		t.Fatalf("refresh after session revocation accepted: %v", err)
	}
}

func TestValidateAccessRejectsFamilyRevocationMarker(t *testing.T) {
	issuer := mustIssuer(t, time.Minute, time.Hour, time.Minute)
	store := &sessionjwt.MemoryJTIStore{}
	issuer.WithJTIStore(store)
	access, _, _, _, err := issuer.IssuePair(sessionjwt.IssuePairParams{
		Subject: "user-1", OrgID: "org-1", Permissions: 8,
	})
	requireNoErr(t, err)
	claims, err := issuer.VerifyAccessProof(sessionjwt.RawToken(access))
	requireNoErr(t, err)
	if err := store.RevokeFamily(context.Background(), claims.FamilyID, time.Hour); err != nil {
		t.Fatal(err)
	}
	if _, err := issuer.ValidateAccess(context.Background(), sessionjwt.RawToken(access)); !errors.Is(err, sessionjwt.ErrInvalidToken) {
		t.Fatalf("access token survived family-only revocation: %v", err)
	}
}

func TestValidateAccessRejectsSessionAndAccessRevocation(t *testing.T) {
	issuer := mustIssuer(t, time.Minute, time.Hour, time.Minute)
	store := &sessionjwt.MemoryJTIStore{}
	issuer.WithJTIStore(store)

	access, _, _, _, err := issuer.IssuePair(sessionjwt.IssuePairParams{
		Subject: "user-1", OrgID: "org-1", Permissions: 8, SessionID: "sid-a", FamilyID: "fam-a",
	})
	requireNoErr(t, err)
	claims, err := issuer.VerifyAccessProof(sessionjwt.RawToken(access))
	requireNoErr(t, err)
	requireNoErr(t, store.RevokeSession(context.Background(), claims.SessionID, time.Hour))
	if _, err := issuer.ValidateAccess(context.Background(), sessionjwt.RawToken(access)); !errors.Is(err, sessionjwt.ErrInvalidToken) {
		t.Fatalf("session-revoked access accepted: %v", err)
	}

	access2, _, _, _, err := issuer.IssuePair(sessionjwt.IssuePairParams{
		Subject: "user-1", OrgID: "org-1", Permissions: 8, SessionID: "sid-b", FamilyID: "fam-b",
	})
	requireNoErr(t, err)
	claims2, err := issuer.VerifyAccessProof(sessionjwt.RawToken(access2))
	requireNoErr(t, err)
	requireNoErr(t, store.RevokeAccess(context.Background(), claims2.JTI, time.Hour))
	if _, err := issuer.ValidateAccess(context.Background(), sessionjwt.RawToken(access2)); !errors.Is(err, sessionjwt.ErrInvalidToken) {
		t.Fatalf("access-jti-revoked token accepted: %v", err)
	}
}

func TestIssuePairMintsFamilyAndSessionWhenEmpty(t *testing.T) {
	issuer := mustIssuer(t, time.Minute, time.Hour, time.Minute)
	access, refresh, _, _, err := issuer.IssuePair(sessionjwt.IssuePairParams{
		Subject: "user-1", OrgID: "org-1", Permissions: 1,
	})
	requireNoErr(t, err)
	accessClaims, err := issuer.ValidateAccess(context.Background(), sessionjwt.RawToken(access))
	requireNoErr(t, err)
	if accessClaims.FamilyID == "" || accessClaims.SessionID == "" {
		t.Fatalf("expected minted family/session, got %+v", accessClaims)
	}
	refreshClaims, err := issuer.VerifyRefreshProof(sessionjwt.RefreshToken(refresh))
	requireNoErr(t, err)
	if refreshClaims.FamilyID != accessClaims.FamilyID || refreshClaims.SessionID != accessClaims.SessionID {
		t.Fatalf("minted pair mismatch access=%+v refresh=%+v", accessClaims, refreshClaims)
	}
}

func TestWithJTIStoreNilGuards(t *testing.T) {
	var nilIssuer *sessionjwt.Issuer
	store := &sessionjwt.MemoryJTIStore{}
	if got := nilIssuer.WithJTIStore(store); got != nil {
		t.Fatalf("nil issuer WithJTIStore: got %#v", got)
	}
	issuer := mustIssuer(t, time.Minute, time.Hour, time.Minute)
	issuer.WithJTIStore(store)
	if got := issuer.WithJTIStore(nil); got != issuer {
		t.Fatal("nil store should leave issuer unchanged")
	}
}

func TestConsumeStepUpRejectsExpectationMismatch(t *testing.T) {
	issuer := mustIssuer(t, time.Minute, time.Hour, time.Minute)
	access, _, _, _, err := issuer.IssuePair(sessionjwt.IssuePairParams{
		Subject: "user-1", OrgID: "org-1", Permissions: 8, SessionID: "sid-1",
	})
	requireNoErr(t, err)
	claims, err := issuer.ValidateAccess(context.Background(), sessionjwt.RawToken(access))
	requireNoErr(t, err)
	step, _, err := issuer.IssueStepUp(sessionjwt.IssueStepUpParams{
		Subject: "user-1", OrgID: "org-1", Permissions: 8, SessionID: claims.SessionID, Action: "legal_hold.manage",
	})
	requireNoErr(t, err)
	cases := []sessionjwt.StepUpExpectations{
		{Subject: "other", OrgID: "org-1", SessionID: claims.SessionID, Action: "legal_hold.manage", RequiredPermission: 8},
		{Subject: "user-1", OrgID: "other", SessionID: claims.SessionID, Action: "legal_hold.manage", RequiredPermission: 8},
		{Subject: "user-1", OrgID: "org-1", SessionID: "other", Action: "legal_hold.manage", RequiredPermission: 8},
		{Subject: "user-1", OrgID: "org-1", SessionID: claims.SessionID, Action: "other.action", RequiredPermission: 8},
		{Subject: "user-1", OrgID: "org-1", SessionID: claims.SessionID, Action: "legal_hold.manage", RequiredPermission: 1 << 30},
	}
	for _, expect := range cases {
		if _, err := issuer.ConsumeStepUp(context.Background(), sessionjwt.RawToken(step), expect); !errors.Is(err, sessionjwt.ErrInvalidToken) {
			t.Fatalf("expected ErrInvalidToken for %+v, got %v", expect, err)
		}
	}
}
