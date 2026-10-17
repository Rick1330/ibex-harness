package policysnapshot

import (
	"crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"encoding/json"
	"encoding/pem"
	"errors"
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

type verifyOpts struct {
	minEpoch int64
	now      time.Time
}

func mustVerify(t *testing.T, set KeySet, opts verifyOpts, params VerifyParams) (Claims, error) {
	t.Helper()
	verifier, err := NewVerifier(VerifierConfig{Keys: set, MinEpoch: opts.minEpoch, Clock: fixedClock(opts.now)})
	if err != nil {
		t.Fatal(err)
	}
	return verifier.Verify(params)
}

// mutationVerifyErr verifies a mutation-class request at baseTime and returns
// the error for assertion, collapsing repeated VerifyParams literals.
func mutationVerifyErr(t *testing.T, set KeySet, envelope Envelope, orgID, agentID string) error {
	t.Helper()
	_, err := mustVerify(t, set, verifyOpts{now: baseTime}, VerifyParams{
		Envelope: envelope, ExpectedOrgID: orgID, ExpectedAgentID: agentID, Class: ClassMutation,
	})
	return err
}

func requireMutationVerifyErr(t *testing.T, set KeySet, envelope Envelope, orgID, agentID string, want error) {
	t.Helper()
	if err := mutationVerifyErr(t, set, envelope, orgID, agentID); !errors.Is(err, want) {
		t.Fatalf("verify err = %v, want %v", err, want)
	}
}

// verifyAt verifies an org-1 mutation-class request at the given clock time.
func verifyAt(t *testing.T, set KeySet, now time.Time, envelope Envelope, class Class) error {
	t.Helper()
	_, err := mustVerify(t, set, verifyOpts{now: now}, VerifyParams{
		Envelope: envelope, ExpectedOrgID: "org-1", Class: class,
	})
	return err
}

// requireExpiredOutcome asserts the freshness outcome for boundary tables.
func requireExpiredOutcome(t *testing.T, err error, wantExpired bool) {
	t.Helper()
	if wantExpired && !errors.Is(err, ErrExpired) {
		t.Fatalf("err = %v, want ErrExpired", err)
	}
	if !wantExpired && err != nil {
		t.Fatalf("err = %v, want nil", err)
	}
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
