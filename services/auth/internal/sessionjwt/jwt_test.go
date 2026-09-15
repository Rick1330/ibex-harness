package sessionjwt_test

import (
	"context"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"encoding/pem"
	"errors"
	"math/big"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/services/auth/internal/sessionjwt"
)

func mustVerifier(t *testing.T, pubPEM, issuer, audience string) *sessionjwt.Verifier {
	t.Helper()
	ver, err := sessionjwt.NewVerifier(sessionjwt.VerifierConfig{
		PublicKeysPEM: sessionjwt.PublicKeysPEM(pubPEM),
		Issuer:        sessionjwt.TokenIssuer(issuer),
		Audience:      sessionjwt.TokenAudience(audience),
	})
	if err != nil {
		t.Fatal(err)
	}
	return ver
}

func testIssuerConfig(privPEM string, access, refresh, stepUp time.Duration) sessionjwt.IssuerConfig {
	return sessionjwt.IssuerConfig{
		PrivateKeyPEM: sessionjwt.PrivateKeyPEM(privPEM),
		Issuer:        sessionjwt.TokenIssuer("ibex-auth"),
		Audience:      sessionjwt.TokenAudience("ibex-dashboard"),
		AccessTTL:     access,
		RefreshTTL:    refresh,
		StepUpTTL:     stepUp,
	}
}

func mustRSAPrivatePEM(t *testing.T) (*rsa.PrivateKey, string) {
	t.Helper()
	priv, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatal(err)
	}
	privPEM := pem.EncodeToMemory(&pem.Block{Type: "RSA PRIVATE KEY", Bytes: x509.MarshalPKCS1PrivateKey(priv)})
	return priv, string(privPEM)
}

func mustPublicPEM(t *testing.T, priv *rsa.PrivateKey) string {
	t.Helper()
	pubDER, err := x509.MarshalPKIXPublicKey(&priv.PublicKey)
	if err != nil {
		t.Fatal(err)
	}
	return string(pem.EncodeToMemory(&pem.Block{Type: "PUBLIC KEY", Bytes: pubDER}))
}

func mustIssuer(t *testing.T, access, refresh, stepUp time.Duration) *sessionjwt.Issuer {
	t.Helper()
	_, privPEM := mustRSAPrivatePEM(t)
	iss, err := sessionjwt.NewIssuer(testIssuerConfig(privPEM, access, refresh, stepUp))
	if err != nil {
		t.Fatal(err)
	}
	return iss
}

func mustIssuerVerifier(t *testing.T) (*sessionjwt.Issuer, *sessionjwt.Verifier) {
	t.Helper()
	priv, privPEM := mustRSAPrivatePEM(t)
	iss, err := sessionjwt.NewIssuer(testIssuerConfig(privPEM, time.Minute, time.Hour, time.Minute))
	if err != nil {
		t.Fatal(err)
	}
	ver, err := sessionjwt.NewVerifier(sessionjwt.VerifierConfig{PublicKeysPEM: sessionjwt.PublicKeysPEM(mustPublicPEM(t, priv)), Issuer: sessionjwt.TokenIssuer("ibex-auth"), Audience: sessionjwt.TokenAudience("ibex-dashboard")})
	if err != nil {
		t.Fatal(err)
	}
	return iss, ver
}

func requireNoErr(t *testing.T, err error) {
	t.Helper()
	if err != nil {
		t.Fatal(err)
	}
}

func TestIssueAndVerify(t *testing.T) {
	t.Parallel()
	iss, ver := mustIssuerVerifier(t)
	access, _, _, _, err := iss.IssuePair(sessionjwt.IssuePairParams{Subject: "user-1", OrgID: "org-1", Permissions: 7})
	requireNoErr(t, err)
	claims, err := ver.Verify(access, sessionjwt.KindAccess)
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
	claims, err := ver.Verify(tok, sessionjwt.KindStepUp)
	requireNoErr(t, err)
	if claims.SessionKind != string(sessionjwt.KindStepUp) {
		t.Fatalf("kind=%q", claims.SessionKind)
	}
	_, err = ver.Verify(tok, sessionjwt.KindAccess)
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
	_, err = ver.Verify("not.a.jwt", sessionjwt.KindAccess)
	if !errors.Is(err, sessionjwt.ErrInvalidToken) {
		t.Fatalf("malformed: %v", err)
	}
}

func TestNewIssuer_DefaultTTLs(t *testing.T) {
	t.Parallel()
	priv, err := rsa.GenerateKey(rand.Reader, 2048)
	requireNoErr(t, err)
	pkcs8, err := x509.MarshalPKCS8PrivateKey(priv)
	requireNoErr(t, err)
	privPEM := string(pem.EncodeToMemory(&pem.Block{Type: "PRIVATE KEY", Bytes: pkcs8}))
	iss, err := sessionjwt.NewIssuer(sessionjwt.IssuerConfig{
		PrivateKeyPEM: sessionjwt.PrivateKeyPEM(privPEM), Issuer: sessionjwt.TokenIssuer("iss"), Audience: sessionjwt.TokenAudience("aud"),
	})
	requireNoErr(t, err)
	access, refresh, aExp, rExp, err := iss.IssuePair(sessionjwt.IssuePairParams{Subject: "u", OrgID: "o", Permissions: 1})
	requireNoErr(t, err)
	if access == "" {
		t.Fatal("empty access")
	}
	if refresh == "" {
		t.Fatal("empty refresh")
	}
	if aExp.IsZero() || rExp.IsZero() {
		t.Fatal("zero expiry")
	}
	ver, err := sessionjwt.NewVerifier(sessionjwt.VerifierConfig{PublicKeysPEM: sessionjwt.PublicKeysPEM(mustPublicPEM(t, priv)), Issuer: sessionjwt.TokenIssuer("iss"), Audience: sessionjwt.TokenAudience("aud")})
	requireNoErr(t, err)
	_, err = ver.Verify(access, sessionjwt.KindAccess)
	requireNoErr(t, err)
}

func TestNewIssuer_RejectsKindAndSignatureMismatch(t *testing.T) {
	t.Parallel()
	priv, privPEM := mustRSAPrivatePEM(t)
	iss, err := sessionjwt.NewIssuer(sessionjwt.IssuerConfig{
		PrivateKeyPEM: sessionjwt.PrivateKeyPEM(privPEM), Issuer: sessionjwt.TokenIssuer("iss"), Audience: sessionjwt.TokenAudience("aud"),
		AccessTTL: time.Minute, RefreshTTL: time.Hour, StepUpTTL: time.Minute,
	})
	requireNoErr(t, err)
	access, refresh, _, _, err := iss.IssuePair(sessionjwt.IssuePairParams{Subject: "u", OrgID: "o", Permissions: 1})
	requireNoErr(t, err)
	pubPEM := mustPublicPEM(t, priv)
	ver, err := sessionjwt.NewVerifier(sessionjwt.VerifierConfig{PublicKeysPEM: sessionjwt.PublicKeysPEM(pubPEM), Issuer: sessionjwt.TokenIssuer("iss"), Audience: sessionjwt.TokenAudience("aud")})
	requireNoErr(t, err)

	_, err = ver.Verify(refresh, sessionjwt.KindAccess)
	if !errors.Is(err, sessionjwt.ErrInvalidToken) {
		t.Fatalf("kind mismatch: %v", err)
	}
	_, err = ver.Verify(access+".extra", sessionjwt.KindAccess)
	if !errors.Is(err, sessionjwt.ErrInvalidToken) {
		t.Fatalf("parts: %v", err)
	}
	parts := splitJWT(access)
	bad := parts[0] + "." + parts[1] + "." + parts[2][:len(parts[2])-2] + "aa"
	_, err = ver.Verify(bad, sessionjwt.KindAccess)
	if !errors.Is(err, sessionjwt.ErrInvalidToken) {
		t.Fatalf("bad sig: %v", err)
	}
	wrongAud, err := sessionjwt.NewVerifier(sessionjwt.VerifierConfig{PublicKeysPEM: sessionjwt.PublicKeysPEM(pubPEM), Issuer: sessionjwt.TokenIssuer("iss"), Audience: sessionjwt.TokenAudience("other")})
	requireNoErr(t, err)
	_, err = wrongAud.Verify(access, sessionjwt.KindAccess)
	if !errors.Is(err, sessionjwt.ErrInvalidToken) {
		t.Fatalf("aud: %v", err)
	}
}

func splitJWT(tok string) []string {
	out := make([]string, 0, 3)
	start := 0
	for i := 0; i < len(tok); i++ {
		if tok[i] == '.' {
			out = append(out, tok[start:i])
			start = i + 1
		}
	}
	out = append(out, tok[start:])
	return out
}

func TestRefreshPair_RejectsAccessTokenAndBadClaims(t *testing.T) {
	t.Parallel()
	iss := mustIssuer(t, time.Minute, time.Hour, time.Minute)
	access, _, _, _, err := iss.IssuePair(sessionjwt.IssuePairParams{Subject: "user-1", OrgID: "org-1", Permissions: 7})
	requireNoErr(t, err)
	_, _, _, _, err = iss.RefreshPair(context.Background(), sessionjwt.RefreshToken(access))
	if !errors.Is(err, sessionjwt.ErrInvalidToken) {
		t.Fatalf("access as refresh: %v", err)
	}
	_, _, _, _, err = iss.RefreshPair(context.Background(), sessionjwt.RefreshToken("not-a-token"))
	if !errors.Is(err, sessionjwt.ErrInvalidToken) {
		t.Fatalf("garbage: %v", err)
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
	_, err = ver.Verify(access, sessionjwt.KindAccess)
	if !errors.Is(err, sessionjwt.ErrExpired) {
		t.Fatalf("want expired, got %v", err)
	}
}

func TestNewVerifier_AcceptsRSACertificatePEM(t *testing.T) {
	t.Parallel()
	priv, err := rsa.GenerateKey(rand.Reader, 2048)
	requireNoErr(t, err)
	tmpl := &x509.Certificate{
		SerialNumber: big.NewInt(1),
		NotBefore:    time.Now().Add(-time.Hour),
		NotAfter:     time.Now().Add(time.Hour),
		KeyUsage:     x509.KeyUsageDigitalSignature,
	}
	certDER, err := x509.CreateCertificate(rand.Reader, tmpl, tmpl, &priv.PublicKey, priv)
	requireNoErr(t, err)
	certPEM := pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: certDER})
	ver, err := sessionjwt.NewVerifier(sessionjwt.VerifierConfig{PublicKeysPEM: sessionjwt.PublicKeysPEM(string(certPEM)), Issuer: sessionjwt.TokenIssuer("iss"), Audience: sessionjwt.TokenAudience("aud")})
	requireNoErr(t, err)
	privPEM := string(pem.EncodeToMemory(&pem.Block{Type: "RSA PRIVATE KEY", Bytes: x509.MarshalPKCS1PrivateKey(priv)}))
	iss, err := sessionjwt.NewIssuer(sessionjwt.IssuerConfig{
		PrivateKeyPEM: sessionjwt.PrivateKeyPEM(privPEM), Issuer: sessionjwt.TokenIssuer("iss"), Audience: sessionjwt.TokenAudience("aud"),
		AccessTTL: time.Minute, RefreshTTL: time.Hour, StepUpTTL: time.Minute,
	})
	requireNoErr(t, err)
	tok, _, err := iss.IssueStepUp(sessionjwt.IssueStepUpParams{Subject: "u", OrgID: "o", Permissions: 1})
	requireNoErr(t, err)
	_, err = ver.Verify(tok, sessionjwt.KindStepUp)
	requireNoErr(t, err)
}

func TestNewVerifier_RejectsNonRSAPublicKey(t *testing.T) {
	t.Parallel()
	ec, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	requireNoErr(t, err)
	pubDER, err := x509.MarshalPKIXPublicKey(&ec.PublicKey)
	requireNoErr(t, err)
	pubPEM := pem.EncodeToMemory(&pem.Block{Type: "PUBLIC KEY", Bytes: pubDER})
	_, err = sessionjwt.NewVerifier(sessionjwt.VerifierConfig{PublicKeysPEM: sessionjwt.PublicKeysPEM(string(pubPEM)), Issuer: sessionjwt.TokenIssuer("i"), Audience: sessionjwt.TokenAudience("a")})
	if err == nil {
		t.Fatal("expected non-RSA public key error")
	}
	_, err = sessionjwt.NewVerifier(sessionjwt.VerifierConfig{PublicKeysPEM: sessionjwt.PublicKeysPEM("\n\n"), Issuer: sessionjwt.TokenIssuer("i"), Audience: sessionjwt.TokenAudience("a")})
	if err == nil {
		t.Fatal("expected no keys")
	}
	pkcs8, err := x509.MarshalPKCS8PrivateKey(ec)
	requireNoErr(t, err)
	ecPrivPEM := string(pem.EncodeToMemory(&pem.Block{Type: "PRIVATE KEY", Bytes: pkcs8}))
	_, err = sessionjwt.NewIssuer(sessionjwt.IssuerConfig{
		PrivateKeyPEM: sessionjwt.PrivateKeyPEM(ecPrivPEM), Issuer: sessionjwt.TokenIssuer("i"), Audience: sessionjwt.TokenAudience("a"),
		AccessTTL: time.Minute, RefreshTTL: time.Hour, StepUpTTL: time.Minute,
	})
	if err == nil {
		t.Fatal("expected non-RSA private key error")
	}
}

func TestVerify_BadSignatureEncoding(t *testing.T) {
	t.Parallel()
	priv, err := rsa.GenerateKey(rand.Reader, 2048)
	requireNoErr(t, err)
	ver, err := sessionjwt.NewVerifier(sessionjwt.VerifierConfig{PublicKeysPEM: sessionjwt.PublicKeysPEM(mustPublicPEM(t, priv)), Issuer: sessionjwt.TokenIssuer("iss"), Audience: sessionjwt.TokenAudience("aud")})
	requireNoErr(t, err)
	_, err = ver.Verify("aaa.bbb.!!!", sessionjwt.KindAccess)
	if !errors.Is(err, sessionjwt.ErrInvalidToken) {
		t.Fatalf("bad b64 sig: %v", err)
	}
	_, err = ver.Verify("aaa.!!! .ccc", sessionjwt.KindAccess)
	if !errors.Is(err, sessionjwt.ErrInvalidToken) {
		t.Fatalf("bad payload: %v", err)
	}
}
