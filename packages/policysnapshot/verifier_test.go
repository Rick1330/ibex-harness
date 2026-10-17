package policysnapshot

import (
	"crypto"
	"crypto/rand"
	"crypto/rsa"
	"errors"
	"testing"
	"time"
)

var baseTime = time.Date(2026, 10, 17, 12, 0, 0, 0, time.UTC)

func signPayload(t *testing.T, key *rsa.PrivateKey, payload []byte) []byte {
	t.Helper()
	signature, err := rsa.SignPKCS1v15(rand.Reader, key, crypto.SHA256, sha256Sum(payload))
	if err != nil {
		t.Fatal(err)
	}
	return signature
}

// baseMutationFixture issues an org-1/agent-1 envelope at baseTime together
// with its signing key and matching key set, collapsing repeated setup trios.
func baseMutationFixture(t *testing.T) (*rsa.PrivateKey, Envelope, KeySet) {
	t.Helper()
	key := mustRSAPrivate(t)
	issuer := mustIssuer(t, key, testIssuerOpts{now: baseTime})
	envelope := mustIssue(t, issuer, "org-1", "agent-1")
	return key, envelope, keySetFrom(t, key, testKeyID)
}

func TestIssueVerifyRoundTrip(t *testing.T) {
	key := mustRSAPrivate(t)
	issuer := mustIssuer(t, key, testIssuerOpts{now: baseTime})
	envelope := mustIssue(t, issuer, "org-1", "agent-1")

	if envelope.Algorithm != AlgorithmRS256 {
		t.Fatalf("algorithm = %q, want %q", envelope.Algorithm, AlgorithmRS256)
	}
	if envelope.KeyID != testKeyID {
		t.Fatalf("key_id = %q, want %q", envelope.KeyID, testKeyID)
	}

	claims, err := mustVerify(t, keySetFrom(t, key, testKeyID), verifyOpts{now: baseTime.Add(time.Second)}, VerifyParams{
		Envelope:        envelope,
		ExpectedOrgID:   "org-1",
		ExpectedAgentID: "agent-1",
		Class:           ClassMutation,
	})
	if err != nil {
		t.Fatalf("verify: %v", err)
	}
	checks := []struct {
		name string
		got  any
		want any
	}{
		{"contract_version", claims.ContractVersion, ContractVersion},
		{"authority", claims.Authority, AuthorityAuthService},
		{"org_id", claims.OrgID, "org-1"},
		{"subject_id", claims.SubjectID, "user-1"},
		{"agent_id", claims.AgentID, "agent-1"},
		{"snapshot_id", claims.SnapshotID, "snapshot-fixed-id"},
		{"epoch", claims.Epoch, int64(1)},
		{"permissions", claims.Permissions, int64(6)},
		{"issued_at", claims.IssuedAt, baseTime.Unix()},
		{"expires_at", claims.ExpiresAt, baseTime.Add(DefaultTTL).Unix()},
	}
	for _, check := range checks {
		if check.got != check.want {
			t.Errorf("%s = %v, want %v", check.name, check.got, check.want)
		}
	}
	if len(claims.Digest) != 64 {
		t.Errorf("digest length = %d, want 64", len(claims.Digest))
	}
}

func TestVerifyRejectsTamperedSignature(t *testing.T) {
	_, envelope, set := baseMutationFixture(t)
	envelope.Signature[0] ^= 0xff

	requireMutationVerifyErr(t, mutationVerifyCase{set: set, envelope: envelope, orgID: "org-1"}, ErrSignatureInvalid)
}

func TestVerifyRejectsTamperedPayload(t *testing.T) {
	_, envelope, set := baseMutationFixture(t)
	envelope.Payload = remarshalClaims(t, envelope.Payload, func(c *Claims) { c.OrgID = "org-2" })

	requireMutationVerifyErr(t, mutationVerifyCase{set: set, envelope: envelope, orgID: "org-2"}, ErrSignatureInvalid)
}

func TestVerifyRejectsDigestMismatch(t *testing.T) {
	key, envelope, set := baseMutationFixture(t)
	envelope.Payload = remarshalClaims(t, envelope.Payload, func(c *Claims) {
		c.Digest = "0000000000000000000000000000000000000000000000000000000000000000"
	})
	envelope.Signature = signPayload(t, key, envelope.Payload)

	requireMutationVerifyErr(t, mutationVerifyCase{set: set, envelope: envelope, orgID: "org-1"}, ErrSignatureInvalid)
}

func TestVerifyRejectsNonCanonicalPayload(t *testing.T) {
	key, envelope, set := baseMutationFixture(t)
	envelope.Payload = append([]byte{' '}, envelope.Payload...)
	envelope.Signature = signPayload(t, key, envelope.Payload)

	requireMutationVerifyErr(t, mutationVerifyCase{set: set, envelope: envelope, orgID: "org-1"}, ErrMalformed)
}

func TestVerifyRejectsMalformedEnvelopes(t *testing.T) {
	_, valid, set := baseMutationFixture(t)

	cases := []struct {
		name   string
		mutate func(*Envelope)
	}{
		{"unsupported algorithm", func(e *Envelope) { e.Algorithm = "none" }},
		{"empty payload", func(e *Envelope) { e.Payload = nil }},
		{"empty signature", func(e *Envelope) { e.Signature = nil }},
		{"oversized payload", func(e *Envelope) { e.Payload = make([]byte, maxPayloadBytes+1) }},
		{"invalid json payload", func(e *Envelope) { e.Payload = []byte("{nope") }},
		{"scalar payload", func(e *Envelope) { e.Payload = []byte("123") }},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			envelope := valid
			envelope.Signature = append([]byte(nil), valid.Signature...)
			envelope.Payload = append([]byte(nil), valid.Payload...)
			tc.mutate(&envelope)
			requireMutationVerifyErr(t, mutationVerifyCase{set: set, envelope: envelope, orgID: "org-1"}, ErrMalformed)
		})
	}
}

func TestVerifyRejectsUnsupportedClaims(t *testing.T) {
	key := mustRSAPrivate(t)
	issuer := mustIssuer(t, key, testIssuerOpts{now: baseTime})
	set := keySetFrom(t, key, testKeyID)

	cases := []struct {
		name   string
		mutate func(*Claims)
	}{
		{"contract version", func(c *Claims) { c.ContractVersion = "policy-snapshot.v2" }},
		{"authority", func(c *Claims) { c.Authority = "rogue" }},
		{"missing org", func(c *Claims) { c.OrgID = "" }},
		{"missing subject", func(c *Claims) { c.SubjectID = "" }},
		{"missing snapshot id", func(c *Claims) { c.SnapshotID = "" }},
		{"zero epoch", func(c *Claims) { c.Epoch = 0 }},
		{"negative permissions", func(c *Claims) { c.Permissions = -1 }},
		{"inverted window", func(c *Claims) { c.ExpiresAt = c.IssuedAt }},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			envelope := mustIssue(t, issuer, "org-1", "agent-1")
			envelope.Payload = remarshalClaims(t, envelope.Payload, tc.mutate)
			envelope.Signature = signPayload(t, key, envelope.Payload)
			requireMutationVerifyErr(t, mutationVerifyCase{set: set, envelope: envelope, orgID: "org-1"}, ErrMalformed)
		})
	}
}

func TestVerifyRejectsUnknownKey(t *testing.T) {
	_, envelope, set := baseMutationFixture(t)
	envelope.KeyID = "v2"

	requireMutationVerifyErr(t, mutationVerifyCase{set: set, envelope: envelope, orgID: "org-1"}, ErrKeyUnknown)
}

func TestVerifyBindingMismatches(t *testing.T) {
	_, envelope, set := baseMutationFixture(t)

	cases := []struct {
		name    string
		org     string
		agent   string
		wantErr error
	}{
		{"cross org", "org-2", "agent-1", ErrOrgMismatch},
		{"missing expected org", "", "agent-1", ErrOrgMismatch},
		{"cross agent", "org-1", "agent-2", ErrAgentMismatch},
		{"empty expected agent skipped", "org-1", "", nil},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			_, err := mustVerify(t, set, verifyOpts{now: baseTime}, VerifyParams{
				Envelope: envelope, ExpectedOrgID: tc.org, ExpectedAgentID: tc.agent, Class: ClassMutation,
			})
			if tc.wantErr == nil {
				if err != nil {
					t.Fatalf("err = %v, want nil", err)
				}
				return
			}
			if !errors.Is(err, tc.wantErr) {
				t.Fatalf("err = %v, want %v", err, tc.wantErr)
			}
		})
	}
}

func TestVerifyFreshnessBoundaries(t *testing.T) {
	_, envelope, set := baseMutationFixture(t)

	cases := []struct {
		name    string
		class   Class
		offset  time.Duration
		wantErr bool
	}{
		{"mutation at 29s accepted", ClassMutation, 29 * time.Second, false},
		{"mutation at max age plus skew accepted", ClassMutation, 35 * time.Second, false},
		{"mutation beyond max age plus skew rejected", ClassMutation, 36 * time.Second, true},
		{"read at 60s accepted", ClassRead, 60 * time.Second, false},
		{"read at max age plus skew accepted", ClassRead, 65 * time.Second, false},
		{"read beyond max age plus skew rejected", ClassRead, 66 * time.Second, true},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			requireExpiredOutcome(t, verifyAt(t, set, baseTime.Add(tc.offset), envelope, tc.class), tc.wantErr)
		})
	}
}

func TestVerifyFutureIssuedBoundaries(t *testing.T) {
	_, envelope, set := baseMutationFixture(t)

	cases := []struct {
		name    string
		offset  time.Duration
		wantErr bool
	}{
		{"within skew accepted", -5 * time.Second, false},
		{"beyond skew rejected", -6 * time.Second, true},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			requireExpiredOutcome(t, verifyAt(t, set, baseTime.Add(tc.offset), envelope, ClassMutation), tc.wantErr)
		})
	}
}

func TestVerifyExpiry(t *testing.T) {
	key := mustRSAPrivate(t)
	set := keySetFrom(t, key, testKeyID)
	issuer := mustIssuer(t, key, testIssuerOpts{now: baseTime, ttl: 10 * time.Second})
	envelope := mustIssue(t, issuer, "org-1", "agent-1")

	cases := []struct {
		name    string
		offset  time.Duration
		wantErr bool
	}{
		{"at expiry plus skew accepted", 15 * time.Second, false},
		{"past expiry plus skew rejected", 16 * time.Second, true},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			requireExpiredOutcome(t, verifyAt(t, set, baseTime.Add(tc.offset), envelope, ClassMutation), tc.wantErr)
		})
	}
}

func TestVerifyEpochFloor(t *testing.T) {
	key := mustRSAPrivate(t)
	set := keySetFrom(t, key, testKeyID)
	oldIssuer := mustIssuer(t, key, testIssuerOpts{now: baseTime, epoch: 1})
	newIssuer := mustIssuer(t, key, testIssuerOpts{now: baseTime, epoch: 2})

	if _, err := mustVerify(t, set, verifyOpts{minEpoch: 2, now: baseTime}, VerifyParams{
		Envelope: mustIssue(t, oldIssuer, "org-1", "agent-1"), ExpectedOrgID: "org-1", Class: ClassMutation,
	}); !errors.Is(err, ErrExpired) {
		t.Fatalf("stale epoch err = %v, want ErrExpired", err)
	}

	claims, err := mustVerify(t, set, verifyOpts{minEpoch: 2, now: baseTime}, VerifyParams{
		Envelope: mustIssue(t, newIssuer, "org-1", "agent-1"), ExpectedOrgID: "org-1", Class: ClassMutation,
	})
	if err != nil {
		t.Fatalf("current epoch verify: %v", err)
	}
	if claims.Epoch != 2 {
		t.Fatalf("epoch = %d, want 2", claims.Epoch)
	}
}

func TestVerifyRotationOverlap(t *testing.T) {
	oldKey := mustRSAPrivate(t)
	newKey := mustRSAPrivate(t)
	oldIssuer := mustIssuer(t, oldKey, testIssuerOpts{now: baseTime, keyID: "v1"})
	newIssuer := mustIssuer(t, newKey, testIssuerOpts{now: baseTime, keyID: "v2", epoch: 2})

	both := map[string]*rsa.PublicKey{"v1": &oldKey.PublicKey, "v2": &newKey.PublicKey}
	rotating, err := NewKeySet(both)
	if err != nil {
		t.Fatal(err)
	}
	oldEnvelope := mustIssue(t, oldIssuer, "org-1", "agent-1")
	if err := mutationVerifyErr(t, mutationVerifyCase{set: rotating, envelope: oldEnvelope, orgID: "org-1"}); err != nil {
		t.Fatalf("overlap verify old key: %v", err)
	}

	retired := keySetFrom(t, newKey, "v2")
	requireMutationVerifyErr(t, mutationVerifyCase{set: retired, envelope: oldEnvelope, orgID: "org-1"}, ErrKeyUnknown)
	newEnvelope := mustIssue(t, newIssuer, "org-1", "agent-1")
	if err := mutationVerifyErr(t, mutationVerifyCase{set: retired, envelope: newEnvelope, orgID: "org-1"}); err != nil {
		t.Fatalf("verify new key: %v", err)
	}
}

func TestClassMaxAge(t *testing.T) {
	if ClassMutation.MaxAge() != 30*time.Second {
		t.Fatalf("mutation max age = %s", ClassMutation.MaxAge())
	}
	if ClassRead.MaxAge() != 60*time.Second {
		t.Fatalf("read max age = %s", ClassRead.MaxAge())
	}
}

func TestClaimsDigestExcludesDigestField(t *testing.T) {
	claims := Claims{
		ContractVersion: ContractVersion, Authority: AuthorityAuthService,
		OrgID: "org-1", SubjectID: "user-1", AgentID: "agent-1", SnapshotID: "s-1",
		Epoch: 1, Permissions: 6, IssuedAt: baseTime.Unix(), ExpiresAt: baseTime.Add(time.Minute).Unix(),
	}
	first, err := claims.computeDigest()
	if err != nil {
		t.Fatal(err)
	}
	claims.Digest = "something-else"
	second, err := claims.computeDigest()
	if err != nil {
		t.Fatal(err)
	}
	if first != second {
		t.Fatalf("digest depends on digest field: %q != %q", first, second)
	}
	claims.OrgID = "org-2"
	third, err := claims.computeDigest()
	if err != nil {
		t.Fatal(err)
	}
	if third == first {
		t.Fatal("digest did not change with claims")
	}
}
