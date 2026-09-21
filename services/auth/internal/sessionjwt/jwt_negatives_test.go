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
	_, err = ver.Verify(sessionjwt.RawToken(access), sessionjwt.KindAccess)
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

	_, err = ver.Verify(sessionjwt.RawToken(refresh), sessionjwt.KindAccess)
	if !errors.Is(err, sessionjwt.ErrInvalidToken) {
		t.Fatalf("kind mismatch: %v", err)
	}
	_, err = ver.Verify(sessionjwt.RawToken(access+".extra"), sessionjwt.KindAccess)
	if !errors.Is(err, sessionjwt.ErrInvalidToken) {
		t.Fatalf("parts: %v", err)
	}
	parts := splitJWT(access)
	bad := parts[0] + "." + parts[1] + "." + parts[2][:len(parts[2])-2] + "aa"
	_, err = ver.Verify(sessionjwt.RawToken(bad), sessionjwt.KindAccess)
	if !errors.Is(err, sessionjwt.ErrInvalidToken) {
		t.Fatalf("bad sig: %v", err)
	}
	wrongAud, err := sessionjwt.NewVerifier(sessionjwt.VerifierConfig{PublicKeysPEM: sessionjwt.PublicKeysPEM(pubPEM), Issuer: sessionjwt.TokenIssuer("iss"), Audience: sessionjwt.TokenAudience("other")})
	requireNoErr(t, err)
	_, err = wrongAud.Verify(sessionjwt.RawToken(access), sessionjwt.KindAccess)
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
	_, err = ver.Verify(sessionjwt.RawToken(tok), sessionjwt.KindStepUp)
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
