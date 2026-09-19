package sessionjwt_test

import (
	"crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"encoding/pem"
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
	return iss, mustVerifier(t, mustPublicPEM(t, priv), "ibex-auth", "ibex-dashboard")
}

func requireNoErr(t *testing.T, err error) {
	t.Helper()
	if err != nil {
		t.Fatal(err)
	}
}
