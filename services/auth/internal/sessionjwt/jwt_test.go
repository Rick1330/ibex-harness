package sessionjwt_test

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/services/auth/internal/sessionjwt"
)

func TestIssueAndVerify(t *testing.T) {
	t.Parallel()
	iss, ver := mustIssuerVerifier(t)
	access, _, _, _, err := iss.IssuePair(sessionjwt.IssuePairParams{Subject: "user-1", OrgID: "org-1", Permissions: 7})
	requireNoErr(t, err)
	claims, err := ver.Verify(sessionjwt.RawToken(access), sessionjwt.KindAccess)
	requireNoErr(t, err)
	if claims.Subject != "user-1" {
		t.Fatalf("subject=%q", claims.Subject)
	}
	if claims.OrgID != "org-1" {
		t.Fatalf("org=%q", claims.OrgID)
	}
	if claims.Permissions != 7 {
		t.Fatalf("permissions=%d", claims.Permissions)
	}
}

func TestRefreshPair_ConsumesJTIOnce(t *testing.T) {
	t.Parallel()
	iss := mustIssuer(t, time.Minute, time.Hour, time.Minute)
	_, refresh, _, _, err := iss.IssuePair(sessionjwt.IssuePairParams{Subject: "user-1", OrgID: "org-1", Permissions: 7})
	requireNoErr(t, err)
	_, _, _, _, err = iss.RefreshPair(context.Background(), sessionjwt.RefreshToken(refresh))
	requireNoErr(t, err)
	_, _, _, _, err = iss.RefreshPair(context.Background(), sessionjwt.RefreshToken(refresh))
	if !errors.Is(err, sessionjwt.ErrInvalidToken) {
		t.Fatalf("replay want ErrInvalidToken, got %v", err)
	}
}

func TestIssueStepUpAndVerify(t *testing.T) {
	t.Parallel()
	iss, ver := mustIssuerVerifier(t)
	tok, exp, err := iss.IssueStepUp(sessionjwt.IssueStepUpParams{Subject: "user-1", OrgID: "org-1", Permissions: 9})
	requireNoErr(t, err)
	if tok == "" {
		t.Fatal("empty step-up token")
	}
	if exp.IsZero() {
		t.Fatal("zero step-up expiry")
	}
	claims, err := ver.Verify(sessionjwt.RawToken(tok), sessionjwt.KindStepUp)
	requireNoErr(t, err)
	if claims.SessionKind != string(sessionjwt.KindStepUp) {
		t.Fatalf("kind=%q", claims.SessionKind)
	}
	_, err = ver.Verify(sessionjwt.RawToken(tok), sessionjwt.KindAccess)
	if !errors.Is(err, sessionjwt.ErrInvalidToken) {
		t.Fatalf("wrong kind: %v", err)
	}
}

func TestVerifierAndIssuerConstructorsRejectBadInput(t *testing.T) {
	t.Parallel()
	_, err := sessionjwt.NewIssuer(sessionjwt.IssuerConfig{
		PrivateKeyPEM: sessionjwt.PrivateKeyPEM("not-pem"), Issuer: sessionjwt.TokenIssuer("i"), Audience: sessionjwt.TokenAudience("a"),
		AccessTTL: time.Minute, RefreshTTL: time.Hour, StepUpTTL: time.Minute,
	})
	if err == nil {
		t.Fatal("expected bad pem")
	}
	_, err = sessionjwt.NewVerifier(sessionjwt.VerifierConfig{PublicKeysPEM: sessionjwt.PublicKeysPEM(""), Issuer: sessionjwt.TokenIssuer("i"), Audience: sessionjwt.TokenAudience("a")})
	if err == nil {
		t.Fatal("expected no keys")
	}
	_, ver := mustIssuerVerifier(t)
	_, err = ver.Verify(sessionjwt.RawToken("not.a.jwt"), sessionjwt.KindAccess)
	if !errors.Is(err, sessionjwt.ErrInvalidToken) {
		t.Fatalf("malformed: %v", err)
	}
}

func TestVerify_Expired(t *testing.T) {
	t.Parallel()
	priv, privPEM := mustRSAPrivatePEM(t)
	iss, err := sessionjwt.NewIssuer(testIssuerConfig(privPEM, time.Second, time.Hour, time.Minute))
	requireNoErr(t, err)
	access, _, _, _, err := iss.IssuePair(sessionjwt.IssuePairParams{Subject: "u", OrgID: "o", Permissions: 1})
	requireNoErr(t, err)
	// Expiry uses unix seconds and is exclusive (< now); wait past exp second.
	time.Sleep(2100 * time.Millisecond)
	ver, err := sessionjwt.NewVerifier(sessionjwt.VerifierConfig{PublicKeysPEM: sessionjwt.PublicKeysPEM(mustPublicPEM(t, priv)), Issuer: sessionjwt.TokenIssuer("ibex-auth"), Audience: sessionjwt.TokenAudience("ibex-dashboard")})
	requireNoErr(t, err)
	_, err = ver.Verify(sessionjwt.RawToken(access), sessionjwt.KindAccess)
	if !errors.Is(err, sessionjwt.ErrExpired) {
		t.Fatalf("want expired, got %v", err)
	}
}

func TestVerify_BadSignatureEncoding(t *testing.T) {
	t.Parallel()
	priv, _ := mustRSAPrivatePEM(t)
	ver := mustVerifier(t, mustPublicPEM(t, priv), "iss", "aud")
	_, err := ver.Verify(sessionjwt.RawToken("aaa.bbb.!!!"), sessionjwt.KindAccess)
	if !errors.Is(err, sessionjwt.ErrInvalidToken) {
		t.Fatalf("bad b64 sig: %v", err)
	}
	_, err = ver.Verify(sessionjwt.RawToken("aaa.!!! .ccc"), sessionjwt.KindAccess)
	if !errors.Is(err, sessionjwt.ErrInvalidToken) {
		t.Fatalf("bad payload: %v", err)
	}
}
