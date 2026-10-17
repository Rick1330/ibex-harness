package policysnapshot

import (
	"bytes"
	"crypto"
	"crypto/rsa"
	"encoding/json"
	"fmt"
	"time"

	"github.com/Rick1330/ibex-harness/packages/canonicaljson"
)

// VerifierConfig configures snapshot verification.
type VerifierConfig struct {
	// Keys is the authority-owned policy-signing key set.
	Keys KeySet
	// MinEpoch rejects snapshots below the accepted effective epoch. Zero
	// accepts any structurally valid epoch.
	MinEpoch int64
	// Clock is injectable for deterministic tests.
	Clock func() time.Time
}

// Verifier validates signed snapshots against the authority key set.
type Verifier struct {
	keys     KeySet
	minEpoch int64
	clock    func() time.Time
}

// NewVerifier validates the key set and configuration.
func NewVerifier(cfg VerifierConfig) (*Verifier, error) {
	if len(cfg.Keys.keys) == 0 {
		return nil, fmt.Errorf("policysnapshot: verifier requires at least one key")
	}
	if cfg.MinEpoch < 0 {
		return nil, fmt.Errorf("policysnapshot: min epoch must be >= 0")
	}
	clock := cfg.Clock
	if clock == nil {
		clock = func() time.Time { return time.Now().UTC() }
	}
	return &Verifier{keys: cfg.Keys, minEpoch: cfg.MinEpoch, clock: clock}, nil
}

// VerifyParams scopes verification to the request being authorized.
type VerifyParams struct {
	Envelope Envelope
	// ExpectedOrgID is the server-derived org for this request. Required.
	ExpectedOrgID string
	// ExpectedAgentID binds the selected agent; empty skips the binding check.
	ExpectedAgentID string
	// Class applies the accepted maximum-age bound.
	Class Class
}

// Verify fail-closed validates envelope, digest, signature, bindings, epoch,
// and freshness, returning the attested claims on success.
func (v *Verifier) Verify(p VerifyParams) (Claims, error) {
	env := p.Envelope
	if env.Algorithm != AlgorithmRS256 {
		return Claims{}, fmt.Errorf("%w: unsupported algorithm", ErrMalformed)
	}
	if len(env.Payload) == 0 || len(env.Payload) > maxPayloadBytes || len(env.Signature) == 0 {
		return Claims{}, fmt.Errorf("%w: invalid envelope", ErrMalformed)
	}
	key, ok := v.keys.Lookup(env.KeyID)
	if !ok {
		return Claims{}, fmt.Errorf("%w: key_id %q", ErrKeyUnknown, env.KeyID)
	}
	claims, err := verifyClaimsPayload(env.Payload)
	if err != nil {
		return Claims{}, err
	}
	if err := verifySignature(key, env.Payload, env.Signature); err != nil {
		return Claims{}, err
	}
	if err := v.verifyAuthorityAndTime(claims, p); err != nil {
		return Claims{}, err
	}
	return claims, nil
}

func verifyClaimsPayload(payload []byte) (Claims, error) {
	canonical, err := canonicaljson.Canonicalize(payload)
	if err != nil {
		return Claims{}, fmt.Errorf("%w: %v", ErrMalformed, err)
	}
	if !bytes.Equal(canonical, payload) {
		return Claims{}, fmt.Errorf("%w: payload is not canonical", ErrMalformed)
	}
	var claims Claims
	if err := json.Unmarshal(payload, &claims); err != nil {
		return Claims{}, fmt.Errorf("%w: parse claims: %v", ErrMalformed, err)
	}
	if err := claims.validateStructure(); err != nil {
		return Claims{}, err
	}
	return claims, nil
}

func verifySignature(key *rsa.PublicKey, payload, signature []byte) error {
	if err := rsa.VerifyPKCS1v15(key, crypto.SHA256, sha256Sum(payload), signature); err != nil {
		return fmt.Errorf("%w: %v", ErrSignatureInvalid, err)
	}
	return nil
}

func (v *Verifier) verifyAuthorityAndTime(claims Claims, p VerifyParams) error {
	if p.ExpectedOrgID == "" || claims.OrgID != p.ExpectedOrgID {
		return fmt.Errorf("%w", ErrOrgMismatch)
	}
	if p.ExpectedAgentID != "" && claims.AgentID != p.ExpectedAgentID {
		return fmt.Errorf("%w", ErrAgentMismatch)
	}
	if err := verifyClaimDigest(claims); err != nil {
		return err
	}
	if claims.Epoch < v.minEpoch {
		return fmt.Errorf("%w: epoch below minimum", ErrExpired)
	}
	return v.verifyFreshness(claims, p.Class)
}

func verifyClaimDigest(claims Claims) error {
	expected, err := claims.computeDigest()
	if err != nil {
		return err
	}
	if claims.Digest != expected {
		return fmt.Errorf("%w: digest mismatch", ErrSignatureInvalid)
	}
	return nil
}

func (v *Verifier) verifyFreshness(claims Claims, class Class) error {
	now := v.clock().UTC()
	issued := time.Unix(claims.IssuedAt, 0).UTC()
	expires := time.Unix(claims.ExpiresAt, 0).UTC()
	if issued.After(now.Add(ClockSkew)) {
		return fmt.Errorf("%w: issued in the future", ErrExpired)
	}
	if now.Sub(issued) > class.MaxAge()+ClockSkew {
		return fmt.Errorf("%w: age exceeds class bound", ErrExpired)
	}
	if now.After(expires.Add(ClockSkew)) {
		return fmt.Errorf("%w: past expiry", ErrExpired)
	}
	return nil
}
