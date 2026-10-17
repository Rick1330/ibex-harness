package main

import (
	"crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"encoding/pem"
	"strings"
	"testing"

	"github.com/Rick1330/ibex-harness/services/auth/internal/config"
)

func testPolicySigningPEM(t *testing.T) string {
	t.Helper()
	key, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatal(err)
	}
	return string(pem.EncodeToMemory(&pem.Block{
		Type: "RSA PRIVATE KEY", Bytes: x509.MarshalPKCS1PrivateKey(key),
	}))
}

func TestUnit_NewPolicySnapshotIssuer(t *testing.T) {
	t.Parallel()
	issuer, err := newPolicySnapshotIssuer(config.Config{})
	if err != nil || issuer != nil {
		t.Fatalf("issuer=%v err=%v want nil,nil without signing key", issuer, err)
	}

	_, err = newPolicySnapshotIssuer(config.Config{PolicySigningKeyPEM: "not-a-pem"})
	if err == nil || !strings.Contains(err.Error(), "policy snapshot issuer") {
		t.Fatalf("err = %v", err)
	}

	issuer, err = newPolicySnapshotIssuer(config.Config{
		PolicySigningKeyPEM: testPolicySigningPEM(t), PolicySigningKeyID: "v9", PolicyEpoch: 3,
	})
	if err != nil {
		t.Fatalf("newPolicySnapshotIssuer: %v", err)
	}
	if issuer == nil || issuer.KeyID() != "v9" || issuer.Epoch() != 3 {
		t.Fatalf("issuer = %+v", issuer)
	}
}

func TestUnit_OptionalPolicyIssuer(t *testing.T) {
	t.Parallel()
	if optionalPolicyIssuer(nil) != nil {
		t.Fatal("expected nil issuer port for nil input")
	}
	issuer, err := newPolicySnapshotIssuer(config.Config{PolicySigningKeyPEM: testPolicySigningPEM(t)})
	if err != nil {
		t.Fatalf("newPolicySnapshotIssuer: %v", err)
	}
	if optionalPolicyIssuer(issuer) == nil {
		t.Fatal("expected non-nil issuer port")
	}
}
