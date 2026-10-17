package policysnapshot

import (
	"crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"encoding/json"
	"encoding/pem"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/canonicaljson"
)

const testKeyID = "v1"

func mustRSAPrivate(t *testing.T) *rsa.PrivateKey {
	t.Helper()
	key, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatal(err)
	}
	return key
}

func mustPrivatePEM(t *testing.T, key *rsa.PrivateKey) string {
	t.Helper()
	return string(pem.EncodeToMemory(&pem.Block{
		Type: "RSA PRIVATE KEY", Bytes: x509.MarshalPKCS1PrivateKey(key),
	}))
}

func mustPublicPEM(t *testing.T, key *rsa.PrivateKey) string {
	t.Helper()
	der, err := x509.MarshalPKIXPublicKey(&key.PublicKey)
	if err != nil {
		t.Fatal(err)
	}
	return string(pem.EncodeToMemory(&pem.Block{Type: "PUBLIC KEY", Bytes: der}))
}

func keySetFrom(t *testing.T, key *rsa.PrivateKey, keyIDs ...string) KeySet {
	t.Helper()
	keys := map[string]*rsa.PublicKey{}
	for _, id := range keyIDs {
		keys[id] = &key.PublicKey
	}
	set, err := NewKeySet(keys)
	if err != nil {
		t.Fatal(err)
	}
	return set
}

func fixedClock(now time.Time) func() time.Time {
	return func() time.Time { return now }
}

type testIssuerOpts struct {
	keyID string
	epoch int64
	ttl   time.Duration
	now   time.Time
}

func mustIssuer(t *testing.T, key *rsa.PrivateKey, opts testIssuerOpts) *Issuer {
	t.Helper()
	keyID := opts.keyID
	if keyID == "" {
		keyID = testKeyID
	}
	epoch := opts.epoch
	if epoch == 0 {
		epoch = 1
	}
	issuer, err := NewIssuer(IssuerConfig{
		PrivateKeyPEM: mustPrivatePEM(t, key),
		KeyID:         keyID,
		Epoch:         epoch,
		TTL:           opts.ttl,
		Clock:         fixedClock(opts.now),
		NewID:         func() string { return "snapshot-fixed-id" },
	})
	if err != nil {
		t.Fatal(err)
	}
	return issuer
}

func mustVerify(t *testing.T, set KeySet, minEpoch int64, now time.Time, params VerifyParams) (Claims, error) {
	t.Helper()
	verifier, err := NewVerifier(VerifierConfig{Keys: set, MinEpoch: minEpoch, Clock: fixedClock(now)})
	if err != nil {
		t.Fatal(err)
	}
	return verifier.Verify(params)
}

func mustIssue(t *testing.T, issuer *Issuer, orgID, agentID string) Envelope {
	t.Helper()
	envelope, err := issuer.Issue(IssueParams{OrgID: orgID, SubjectID: "user-1", AgentID: agentID, Permissions: 6})
	if err != nil {
		t.Fatal(err)
	}
	return envelope
}

func remarshalClaims(t *testing.T, payload []byte, mutate func(*Claims)) []byte {
	t.Helper()
	var claims Claims
	if err := json.Unmarshal(payload, &claims); err != nil {
		t.Fatal(err)
	}
	mutate(&claims)
	raw, err := json.Marshal(claims)
	if err != nil {
		t.Fatal(err)
	}
	canonical, err := canonicaljson.Canonicalize(raw)
	if err != nil {
		t.Fatal(err)
	}
	return canonical
}
