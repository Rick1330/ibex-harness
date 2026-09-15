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

func TestIssueAndVerify(t *testing.T) {
	t.Parallel()
	priv, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatal(err)
	}
	privPEM := pem.EncodeToMemory(&pem.Block{Type: "RSA PRIVATE KEY", Bytes: x509.MarshalPKCS1PrivateKey(priv)})
	pubDER, err := x509.MarshalPKIXPublicKey(&priv.PublicKey)
	if err != nil {
		t.Fatal(err)
	}
	pubPEM := pem.EncodeToMemory(&pem.Block{Type: "PUBLIC KEY", Bytes: pubDER})

	iss, err := sessionjwt.NewIssuer(string(privPEM), "ibex-auth", "ibex-dashboard", time.Minute, time.Hour, time.Minute)
	if err != nil {
		t.Fatal(err)
	}
	access, _, _, _, err := iss.IssuePair("user-1", "org-1", 7)
	if err != nil {
		t.Fatal(err)
	}
	ver, err := sessionjwt.NewVerifier(string(pubPEM), "ibex-auth", "ibex-dashboard")
	if err != nil {
		t.Fatal(err)
	}
	claims, err := ver.Verify(access, sessionjwt.KindAccess)
	if err != nil {
		t.Fatal(err)
	}
	if claims.Subject != "user-1" || claims.OrgID != "org-1" || claims.Permissions != 7 {
		t.Fatalf("claims=%+v", claims)
	}
}

func TestRefreshPair_ConsumesJTIOnce(t *testing.T) {
	t.Parallel()
	priv, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatal(err)
	}
	privPEM := pem.EncodeToMemory(&pem.Block{Type: "RSA PRIVATE KEY", Bytes: x509.MarshalPKCS1PrivateKey(priv)})
	iss, err := sessionjwt.NewIssuer(string(privPEM), "ibex-auth", "ibex-dashboard", time.Minute, time.Hour, time.Minute)
	if err != nil {
		t.Fatal(err)
	}
	_, refresh, _, _, err := iss.IssuePair("user-1", "org-1", 7)
	if err != nil {
		t.Fatal(err)
	}
	if _, _, _, _, err := iss.RefreshPair(context.Background(), refresh); err != nil {
		t.Fatalf("first refresh: %v", err)
	}
	if _, _, _, _, err := iss.RefreshPair(context.Background(), refresh); !errors.Is(err, sessionjwt.ErrInvalidToken) {
		t.Fatalf("replay want ErrInvalidToken, got %v", err)
	}
}

func TestIssueStepUpAndVerifyNegatives(t *testing.T) {
	t.Parallel()
	priv, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatal(err)
	}
	privPEM := pem.EncodeToMemory(&pem.Block{Type: "RSA PRIVATE KEY", Bytes: x509.MarshalPKCS1PrivateKey(priv)})
	pubDER, err := x509.MarshalPKIXPublicKey(&priv.PublicKey)
	if err != nil {
		t.Fatal(err)
	}
	pubPEM := pem.EncodeToMemory(&pem.Block{Type: "PUBLIC KEY", Bytes: pubDER})
	iss, err := sessionjwt.NewIssuer(string(privPEM), "ibex-auth", "ibex-dashboard", time.Minute, time.Hour, time.Minute)
	if err != nil {
		t.Fatal(err)
	}
	tok, exp, err := iss.IssueStepUp("user-1", "org-1", 9)
	if err != nil || tok == "" || exp.IsZero() {
		t.Fatalf("stepup: %v", err)
	}
	ver, err := sessionjwt.NewVerifier(string(pubPEM), "ibex-auth", "ibex-dashboard")
	if err != nil {
		t.Fatal(err)
	}
	claims, err := ver.Verify(tok, sessionjwt.KindStepUp)
	if err != nil || claims.SessionKind != sessionjwt.KindStepUp {
		t.Fatalf("verify stepup: %+v err=%v", claims, err)
	}
	if _, err := ver.Verify(tok, sessionjwt.KindAccess); !errors.Is(err, sessionjwt.ErrInvalidToken) {
		t.Fatalf("wrong kind: %v", err)
	}
	if _, err := ver.Verify("not.a.jwt", sessionjwt.KindAccess); !errors.Is(err, sessionjwt.ErrInvalidToken) {
		t.Fatalf("malformed: %v", err)
	}
	if _, err := sessionjwt.NewIssuer("not-pem", "i", "a", time.Minute, time.Hour, time.Minute); err == nil {
		t.Fatal("expected bad pem")
	}
	if _, err := sessionjwt.NewVerifier("", "i", "a"); err == nil {
		t.Fatal("expected no keys")
	}
}

func TestNewIssuer_DefaultTTLsAndPKCS8(t *testing.T) {
	t.Parallel()
	priv, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatal(err)
	}
	pkcs8, err := x509.MarshalPKCS8PrivateKey(priv)
	if err != nil {
		t.Fatal(err)
	}
	privPEM := pem.EncodeToMemory(&pem.Block{Type: "PRIVATE KEY", Bytes: pkcs8})
	iss, err := sessionjwt.NewIssuer(string(privPEM), "iss", "aud", 0, 0, 0)
	if err != nil {
		t.Fatal(err)
	}
	access, refresh, aExp, rExp, err := iss.IssuePair("u", "o", 1)
	if err != nil || access == "" || refresh == "" || aExp.IsZero() || rExp.IsZero() {
		t.Fatalf("pair: %v", err)
	}
	pubDER, err := x509.MarshalPKIXPublicKey(&priv.PublicKey)
	if err != nil {
		t.Fatal(err)
	}
	pubPEM := pem.EncodeToMemory(&pem.Block{Type: "PUBLIC KEY", Bytes: pubDER})
	ver, err := sessionjwt.NewVerifier(string(pubPEM), "iss", "aud")
	if err != nil {
		t.Fatal(err)
	}
	if _, err := ver.Verify(access, sessionjwt.KindAccess); err != nil {
		t.Fatal(err)
	}
	if _, err := ver.Verify(refresh, sessionjwt.KindAccess); !errors.Is(err, sessionjwt.ErrInvalidToken) {
		t.Fatalf("kind mismatch: %v", err)
	}
	if _, err := ver.Verify(access+".extra", sessionjwt.KindAccess); !errors.Is(err, sessionjwt.ErrInvalidToken) {
		t.Fatalf("parts: %v", err)
	}
	// Tamper signature.
	parts := splitJWT(access)
	bad := parts[0] + "." + parts[1] + "." + parts[2][:len(parts[2])-2] + "aa"
	if _, err := ver.Verify(bad, sessionjwt.KindAccess); !errors.Is(err, sessionjwt.ErrInvalidToken) {
		t.Fatalf("bad sig: %v", err)
	}
	wrongAud, err := sessionjwt.NewVerifier(string(pubPEM), "iss", "other")
	if err != nil {
		t.Fatal(err)
	}
	if _, err := wrongAud.Verify(access, sessionjwt.KindAccess); !errors.Is(err, sessionjwt.ErrInvalidToken) {
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
	priv, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatal(err)
	}
	privPEM := pem.EncodeToMemory(&pem.Block{Type: "RSA PRIVATE KEY", Bytes: x509.MarshalPKCS1PrivateKey(priv)})
	iss, err := sessionjwt.NewIssuer(string(privPEM), "ibex-auth", "ibex-dashboard", time.Minute, time.Hour, time.Minute)
	if err != nil {
		t.Fatal(err)
	}
	access, _, _, _, err := iss.IssuePair("user-1", "org-1", 7)
	if err != nil {
		t.Fatal(err)
	}
	if _, _, _, _, err := iss.RefreshPair(context.Background(), access); !errors.Is(err, sessionjwt.ErrInvalidToken) {
		t.Fatalf("access as refresh: %v", err)
	}
	if _, _, _, _, err := iss.RefreshPair(context.Background(), "not-a-token"); !errors.Is(err, sessionjwt.ErrInvalidToken) {
		t.Fatalf("garbage: %v", err)
	}
}

func TestVerify_Expired(t *testing.T) {
	t.Parallel()
	priv, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatal(err)
	}
	privPEM := pem.EncodeToMemory(&pem.Block{Type: "RSA PRIVATE KEY", Bytes: x509.MarshalPKCS1PrivateKey(priv)})
	iss, err := sessionjwt.NewIssuer(string(privPEM), "ibex-auth", "ibex-dashboard", time.Second, time.Hour, time.Minute)
	if err != nil {
		t.Fatal(err)
	}
	access, _, _, _, err := iss.IssuePair("u", "o", 1)
	if err != nil {
		t.Fatal(err)
	}
	// Expiry uses unix seconds and is exclusive (< now); wait past exp second.
	time.Sleep(2100 * time.Millisecond)
	pubDER, err := x509.MarshalPKIXPublicKey(&priv.PublicKey)
	if err != nil {
		t.Fatal(err)
	}
	pubPEM := pem.EncodeToMemory(&pem.Block{Type: "PUBLIC KEY", Bytes: pubDER})
	ver, err := sessionjwt.NewVerifier(string(pubPEM), "ibex-auth", "ibex-dashboard")
	if err != nil {
		t.Fatal(err)
	}
	if _, err := ver.Verify(access, sessionjwt.KindAccess); !errors.Is(err, sessionjwt.ErrExpired) {
		t.Fatalf("want expired, got %v", err)
	}
}

func TestNewVerifier_AcceptsRSACertificatePEM(t *testing.T) {
	t.Parallel()
	priv, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatal(err)
	}
	tmpl := &x509.Certificate{
		SerialNumber: big.NewInt(1),
		NotBefore:    time.Now().Add(-time.Hour),
		NotAfter:     time.Now().Add(time.Hour),
		KeyUsage:     x509.KeyUsageDigitalSignature,
	}
	certDER, err := x509.CreateCertificate(rand.Reader, tmpl, tmpl, &priv.PublicKey, priv)
	if err != nil {
		t.Fatal(err)
	}
	certPEM := pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: certDER})
	ver, err := sessionjwt.NewVerifier(string(certPEM), "iss", "aud")
	if err != nil {
		t.Fatal(err)
	}
	privPEM := pem.EncodeToMemory(&pem.Block{Type: "RSA PRIVATE KEY", Bytes: x509.MarshalPKCS1PrivateKey(priv)})
	iss, err := sessionjwt.NewIssuer(string(privPEM), "iss", "aud", time.Minute, time.Hour, time.Minute)
	if err != nil {
		t.Fatal(err)
	}
	tok, _, err := iss.IssueStepUp("u", "o", 1)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := ver.Verify(tok, sessionjwt.KindStepUp); err != nil {
		t.Fatal(err)
	}
}

func TestNewVerifier_RejectsNonRSAPublicKey(t *testing.T) {
	t.Parallel()
	ec, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	pubDER, err := x509.MarshalPKIXPublicKey(&ec.PublicKey)
	if err != nil {
		t.Fatal(err)
	}
	pubPEM := pem.EncodeToMemory(&pem.Block{Type: "PUBLIC KEY", Bytes: pubDER})
	if _, err := sessionjwt.NewVerifier(string(pubPEM), "i", "a"); err == nil {
		t.Fatal("expected non-RSA public key error")
	}
	if _, err := sessionjwt.NewVerifier("\n\n", "i", "a"); err == nil {
		t.Fatal("expected no keys")
	}
	pkcs8, err := x509.MarshalPKCS8PrivateKey(ec)
	if err != nil {
		t.Fatal(err)
	}
	ecPrivPEM := pem.EncodeToMemory(&pem.Block{Type: "PRIVATE KEY", Bytes: pkcs8})
	if _, err := sessionjwt.NewIssuer(string(ecPrivPEM), "i", "a", time.Minute, time.Hour, time.Minute); err == nil {
		t.Fatal("expected non-RSA private key error")
	}
}

func TestVerify_BadSignatureEncoding(t *testing.T) {
	t.Parallel()
	priv, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatal(err)
	}
	pubDER, err := x509.MarshalPKIXPublicKey(&priv.PublicKey)
	if err != nil {
		t.Fatal(err)
	}
	pubPEM := pem.EncodeToMemory(&pem.Block{Type: "PUBLIC KEY", Bytes: pubDER})
	ver, err := sessionjwt.NewVerifier(string(pubPEM), "iss", "aud")
	if err != nil {
		t.Fatal(err)
	}
	if _, err := ver.Verify("aaa.bbb.!!!", sessionjwt.KindAccess); !errors.Is(err, sessionjwt.ErrInvalidToken) {
		t.Fatalf("bad b64 sig: %v", err)
	}
	if _, err := ver.Verify("aaa.!!! .ccc", sessionjwt.KindAccess); !errors.Is(err, sessionjwt.ErrInvalidToken) {
		t.Fatalf("bad payload: %v", err)
	}
}
