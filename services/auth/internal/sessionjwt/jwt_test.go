package sessionjwt_test

import (
	"crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"encoding/pem"
	"errors"
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
	if _, _, _, _, err := iss.RefreshPair(refresh); err != nil {
		t.Fatalf("first refresh: %v", err)
	}
	if _, _, _, _, err := iss.RefreshPair(refresh); !errors.Is(err, sessionjwt.ErrInvalidToken) {
		t.Fatalf("replay want ErrInvalidToken, got %v", err)
	}
}
