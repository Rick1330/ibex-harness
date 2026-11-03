package policysnapshot

import (
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/json"
	"encoding/pem"
	"math/big"
	"strings"
	"testing"
	"time"
)

func TestNewIssuerValidation(t *testing.T) {
	key := mustRSAPrivate(t)
	validPEM := mustPrivatePEM(t, key)

	cases := []struct {
		name string
		cfg  IssuerConfig
	}{
		{"empty pem", IssuerConfig{KeyID: "v1", Epoch: 1}},
		{"invalid pem", IssuerConfig{PrivateKeyPEM: "not-a-pem", KeyID: "v1", Epoch: 1}},
		{"empty key id", IssuerConfig{PrivateKeyPEM: validPEM, Epoch: 1}},
		{"zero epoch", IssuerConfig{PrivateKeyPEM: validPEM, KeyID: "v1"}},
		{"unknown authority", IssuerConfig{PrivateKeyPEM: validPEM, KeyID: "v1", Epoch: 1, Authority: "rogue"}},
		{"sub-second ttl", IssuerConfig{PrivateKeyPEM: validPEM, KeyID: "v1", Epoch: 1, TTL: 500 * time.Millisecond}},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			if _, err := NewIssuer(tc.cfg); err == nil {
				t.Fatal("NewIssuer accepted invalid config")
			}
		})
	}

	issuer, err := NewIssuer(IssuerConfig{PrivateKeyPEM: validPEM, KeyID: "v1", Epoch: 2})
	if err != nil {
		t.Fatalf("valid config: %v", err)
	}
	if issuer.KeyID() != "v1" || issuer.Epoch() != 2 {
		t.Fatalf("key_id/epoch = %q/%d", issuer.KeyID(), issuer.Epoch())
	}
}

func TestNewIssuerRejectsWeakKey(t *testing.T) {
	// The undersized key is a throwaway fixture that must be rejected; it is
	// never used for real signing.
	weak, err := rsa.GenerateKey(rand.Reader, 1024) // nosemgrep -- throwaway fixture asserting weak keys are rejected
	if err != nil {
		t.Fatal(err)
	}
	weakPEM := string(pem.EncodeToMemory(&pem.Block{
		Type: "RSA PRIVATE KEY", Bytes: x509.MarshalPKCS1PrivateKey(weak),
	}))
	if _, err := NewIssuer(IssuerConfig{PrivateKeyPEM: weakPEM, KeyID: "v1", Epoch: 1}); err == nil {
		t.Fatal("NewIssuer accepted a 1024-bit key")
	}
}

func TestNewIssuerAcceptsPKCS8(t *testing.T) {
	key := mustRSAPrivate(t)
	der, err := x509.MarshalPKCS8PrivateKey(key)
	if err != nil {
		t.Fatal(err)
	}
	pkcs8 := string(pem.EncodeToMemory(&pem.Block{Type: "PRIVATE KEY", Bytes: der}))
	if _, err := NewIssuer(IssuerConfig{PrivateKeyPEM: pkcs8, KeyID: "v1", Epoch: 1}); err != nil {
		t.Fatalf("PKCS#8 key rejected: %v", err)
	}
}

func TestIssueValidation(t *testing.T) {
	key := mustRSAPrivate(t)
	issuer := mustIssuer(t, key, testIssuerOpts{now: baseTime})

	cases := []struct {
		name   string
		params IssueParams
	}{
		{"missing org", IssueParams{SubjectID: "user-1", Permissions: 1}},
		{"missing subject", IssueParams{OrgID: "org-1", Permissions: 1}},
		{"negative permissions", IssueParams{OrgID: "org-1", SubjectID: "user-1", Permissions: -1}},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			if _, err := issuer.Issue(tc.params); err == nil {
				t.Fatal("Issue accepted invalid params")
			}
		})
	}
}

func TestIssueWithDefaultClockUsesWallTime(t *testing.T) {
	key := mustRSAPrivate(t)
	issuer, err := NewIssuer(IssuerConfig{
		PrivateKeyPEM: mustPrivatePEM(t, key), KeyID: "v1", Epoch: 1,
	})
	if err != nil {
		t.Fatalf("NewIssuer: %v", err)
	}
	before := time.Now().UTC().Unix()
	envelope, err := issuer.Issue(IssueParams{OrgID: "org-1", SubjectID: "user-1", Permissions: 1})
	if err != nil {
		t.Fatalf("Issue: %v", err)
	}
	var claims Claims
	if err := json.Unmarshal(envelope.Payload, &claims); err != nil {
		t.Fatalf("unmarshal claims: %v", err)
	}
	after := time.Now().UTC().Unix()
	if claims.IssuedAt < before || claims.IssuedAt > after {
		t.Fatalf("issued_at = %d not within [%d, %d]", claims.IssuedAt, before, after)
	}
}

func TestParseKeySetJSON(t *testing.T) {
	key := mustRSAPrivate(t)
	pubPEM := mustPublicPEM(t, key)
	valid := map[string]string{"v1": pubPEM}
	raw, err := json.Marshal(valid)
	if err != nil {
		t.Fatal(err)
	}

	set, err := ParseKeySetJSON(string(raw))
	if err != nil {
		t.Fatalf("valid key set: %v", err)
	}
	if _, ok := set.Lookup("v1"); !ok {
		t.Fatal("v1 not found in key set")
	}
	if ids := set.KeyIDs(); len(ids) != 1 || ids[0] != "v1" {
		t.Fatalf("key ids = %v", ids)
	}

	cases := []struct {
		name string
		raw  string
	}{
		{"empty", ""},
		{"not json", "{"},
		{"empty object", "{}"},
		{"bad pem", `{"v1":"not-a-pem"}`},
		{"empty id", `{"":"` + strings.ReplaceAll(pubPEM, "\n", `\n`) + `"}`},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			if _, err := ParseKeySetJSON(tc.raw); err == nil {
				t.Fatal("ParseKeySetJSON accepted invalid input")
			}
		})
	}
}

func TestParseKeySetJSONCertificate(t *testing.T) {
	key := mustRSAPrivate(t)
	template := &x509.Certificate{
		SerialNumber: big.NewInt(1),
		Subject:      pkix.Name{CommonName: "ibex-policy"},
		NotBefore:    baseTime.Add(-time.Hour),
		NotAfter:     baseTime.Add(time.Hour),
	}
	der, err := x509.CreateCertificate(rand.Reader, template, template, &key.PublicKey, key)
	if err != nil {
		t.Fatal(err)
	}
	certPEM := string(pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: der}))
	raw, err := json.Marshal(map[string]string{"v1": certPEM})
	if err != nil {
		t.Fatal(err)
	}
	set, err := ParseKeySetJSON(string(raw))
	if err != nil {
		t.Fatalf("certificate key set: %v", err)
	}
	if _, ok := set.Lookup("v1"); !ok {
		t.Fatal("certificate key not found")
	}
}

func TestNewKeySetValidation(t *testing.T) {
	key := mustRSAPrivate(t)
	if _, err := NewKeySet(nil); err == nil {
		t.Fatal("NewKeySet accepted empty map")
	}
	if _, err := NewKeySet(map[string]*rsa.PublicKey{"": &key.PublicKey}); err == nil {
		t.Fatal("NewKeySet accepted empty id")
	}
	if _, err := NewKeySet(map[string]*rsa.PublicKey{"v1": nil}); err == nil {
		t.Fatal("NewKeySet accepted nil key")
	}
}

func TestNewVerifierValidation(t *testing.T) {
	if _, err := NewVerifier(VerifierConfig{}); err == nil {
		t.Fatal("NewVerifier accepted empty key set")
	}
	key := mustRSAPrivate(t)
	if _, err := NewVerifier(VerifierConfig{
		Keys: keySetFrom(t, key, testKeyID), MinEpoch: -1,
	}); err == nil {
		t.Fatal("NewVerifier accepted negative min epoch")
	}
	verifier, err := NewVerifier(VerifierConfig{Keys: keySetFrom(t, key, testKeyID)})
	if err != nil {
		t.Fatalf("NewVerifier with default clock: %v", err)
	}
	if verifier == nil {
		t.Fatal("NewVerifier returned nil")
	}
}

func TestVerifyWithDefaultClockUsesWallTime(t *testing.T) {
	key := mustRSAPrivate(t)
	issuer := mustIssuer(t, key, testIssuerOpts{now: time.Now().UTC().Add(-5 * time.Second)})
	envelope := mustIssue(t, issuer, "org-1", "agent-1")
	verifier, err := NewVerifier(VerifierConfig{Keys: keySetFrom(t, key, testKeyID)})
	if err != nil {
		t.Fatal(err)
	}
	claims, err := verifier.Verify(VerifyParams{
		Envelope: envelope, ExpectedOrgID: "org-1", ExpectedAgentID: "agent-1", Class: ClassMutation,
	})
	if err != nil {
		t.Fatalf("default-clock verify: %v", err)
	}
	if claims.OrgID != "org-1" {
		t.Fatalf("org = %q, want org-1", claims.OrgID)
	}
}

func TestParsePublicKeyPEMRejectsUndecodableBlock(t *testing.T) {
	pemData := string(pem.EncodeToMemory(&pem.Block{Type: "PUBLIC KEY", Bytes: []byte("not a key")}))
	if _, err := ParsePublicKeyPEM(pemData); err == nil {
		t.Fatal("ParsePublicKeyPEM accepted a non-key PEM block")
	}
}

func TestParsePublicKeyPEMRejectsNonRSA(t *testing.T) {
	ecKey, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	der, err := x509.MarshalPKIXPublicKey(&ecKey.PublicKey)
	if err != nil {
		t.Fatal(err)
	}
	ecPEM := string(pem.EncodeToMemory(&pem.Block{Type: "PUBLIC KEY", Bytes: der}))
	if _, err := ParsePublicKeyPEM(ecPEM); err == nil {
		t.Fatal("ParsePublicKeyPEM accepted an EC key")
	}

	template := &x509.Certificate{
		SerialNumber: big.NewInt(2),
		Subject:      pkix.Name{CommonName: "ibex-policy-ec"},
		NotBefore:    baseTime.Add(-time.Hour),
		NotAfter:     baseTime.Add(time.Hour),
	}
	certDER, err := x509.CreateCertificate(rand.Reader, template, template, &ecKey.PublicKey, ecKey)
	if err != nil {
		t.Fatal(err)
	}
	ecCertPEM := string(pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: certDER}))
	if _, err := ParsePublicKeyPEM(ecCertPEM); err == nil {
		t.Fatal("ParsePublicKeyPEM accepted an EC certificate")
	}
}

func TestNewIssuerRejectsNonRSAPrivateKeys(t *testing.T) {
	ecKey, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	ecDER, err := x509.MarshalPKCS8PrivateKey(ecKey)
	if err != nil {
		t.Fatal(err)
	}
	ecPEM := string(pem.EncodeToMemory(&pem.Block{Type: "PRIVATE KEY", Bytes: ecDER}))
	if _, err := NewIssuer(IssuerConfig{PrivateKeyPEM: ecPEM, KeyID: "v1", Epoch: 1}); err == nil {
		t.Fatal("NewIssuer accepted an EC private key")
	}

	garbagePEM := string(pem.EncodeToMemory(&pem.Block{Type: "PRIVATE KEY", Bytes: []byte("garbage")}))
	if _, err := NewIssuer(IssuerConfig{PrivateKeyPEM: garbagePEM, KeyID: "v1", Epoch: 1}); err == nil {
		t.Fatal("NewIssuer accepted a malformed private key")
	}
}
