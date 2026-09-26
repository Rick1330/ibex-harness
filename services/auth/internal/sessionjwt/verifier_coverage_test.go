package sessionjwt_test

import (
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/services/auth/internal/sessionjwt"
)

func TestNewVerifier_DefaultKeyIDAcceptsV1(t *testing.T) {
	priv, privPEM := mustRSAPrivatePEM(t)
	pub := mustPublicPEM(t, priv)
	iss, err := sessionjwt.NewIssuer(testIssuerConfig(privPEM, time.Minute, time.Hour, time.Minute))
	requireNoErr(t, err)
	ver, err := sessionjwt.NewVerifier(sessionjwt.VerifierConfig{
		PublicKeysPEM: sessionjwt.PublicKeysPEM(pub),
		Issuer:        sessionjwt.TokenIssuer("ibex-auth"),
		Audience:      sessionjwt.TokenAudience("ibex-dashboard"),
		KeyID:         "",
	})
	requireNoErr(t, err)
	access, _, _, _, err := iss.IssuePair(sessionjwt.IssuePairParams{Subject: "u", OrgID: "o", Permissions: 1})
	requireNoErr(t, err)
	if _, err := ver.Verify(sessionjwt.RawToken(access), sessionjwt.KindAccess); err != nil {
		t.Fatal(err)
	}
}

func TestVerify_RejectsKeyIDMismatch(t *testing.T) {
	priv, privPEM := mustRSAPrivatePEM(t)
	pub := mustPublicPEM(t, priv)
	iss, err := sessionjwt.NewIssuer(testIssuerConfig(privPEM, time.Minute, time.Hour, time.Minute))
	requireNoErr(t, err)
	ver, err := sessionjwt.NewVerifier(sessionjwt.VerifierConfig{
		PublicKeysPEM: sessionjwt.PublicKeysPEM(pub),
		Issuer:        sessionjwt.TokenIssuer("ibex-auth"),
		Audience:      sessionjwt.TokenAudience("ibex-dashboard"),
		KeyID:         "v2",
	})
	requireNoErr(t, err)
	access, _, _, _, err := iss.IssuePair(sessionjwt.IssuePairParams{Subject: "u", OrgID: "o", Permissions: 1})
	requireNoErr(t, err)
	if _, err := ver.Verify(sessionjwt.RawToken(access), sessionjwt.KindAccess); err == nil {
		t.Fatal("expected kid mismatch")
	}
}

func TestVerify_AcceptsSecondPublicKeyInPEMSet(t *testing.T) {
	priv1, privPEM1 := mustRSAPrivatePEM(t)
	priv2, _ := mustRSAPrivatePEM(t)
	pub1 := mustPublicPEM(t, priv1)
	pub2 := mustPublicPEM(t, priv2)
	iss, err := sessionjwt.NewIssuer(testIssuerConfig(privPEM1, time.Minute, time.Hour, time.Minute))
	requireNoErr(t, err)
	ver, err := sessionjwt.NewVerifier(sessionjwt.VerifierConfig{
		PublicKeysPEM: sessionjwt.PublicKeysPEM(pub2 + "\n" + pub1),
		Issuer:        sessionjwt.TokenIssuer("ibex-auth"),
		Audience:      sessionjwt.TokenAudience("ibex-dashboard"),
	})
	requireNoErr(t, err)
	access, _, _, _, err := iss.IssuePair(sessionjwt.IssuePairParams{Subject: "u", OrgID: "o", Permissions: 1})
	requireNoErr(t, err)
	if _, err := ver.Verify(sessionjwt.RawToken(access), sessionjwt.KindAccess); err != nil {
		t.Fatal(err)
	}
}

func TestVerify_AccessAndRefreshKinds(t *testing.T) {
	priv, privPEM := mustRSAPrivatePEM(t)
	pub := mustPublicPEM(t, priv)
	iss, err := sessionjwt.NewIssuer(testIssuerConfig(privPEM, time.Minute, time.Hour, time.Minute))
	requireNoErr(t, err)
	ver := mustVerifier(t, pub, "ibex-auth", "ibex-dashboard")
	access, refresh, _, _, err := iss.IssuePair(sessionjwt.IssuePairParams{Subject: "u", OrgID: "o", Permissions: 1})
	requireNoErr(t, err)
	if _, err := ver.Verify(sessionjwt.RawToken(access), sessionjwt.KindAccess); err != nil {
		t.Fatal(err)
	}
	if _, err := ver.Verify(sessionjwt.RawToken(refresh), sessionjwt.KindRefresh); err != nil {
		t.Fatal(err)
	}
	if _, err := ver.Verify(sessionjwt.RawToken(access), sessionjwt.KindRefresh); err == nil {
		t.Fatal("access token must not verify as refresh")
	}
}
