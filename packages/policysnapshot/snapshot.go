// Package policysnapshot implements the signed policy-snapshot seam accepted in
// the G0 owner decision record (21-g0-owner-decision-record.md §2.1-2.2):
// AuthService issues immutable RS256-signed envelopes and consumers verify
// them against the AuthService policy-signing key set before any effect.
package policysnapshot

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/Rick1330/ibex-harness/packages/canonicaljson"
)

const (
	// ContractVersion identifies the policy-snapshot claim schema.
	ContractVersion = "policy-snapshot.v1"
	// AuthorityAuthService is the accepted policy-signing authority identity.
	AuthorityAuthService = "AuthService"
	// AlgorithmRS256 is the only supported envelope signature algorithm.
	AlgorithmRS256 = "RS256"
)

const (
	// ClassMutationMaxAge bounds mutating/externally effectful requests.
	ClassMutationMaxAge = 30 * time.Second
	// ClassReadMaxAge bounds protected reads and context assembly.
	ClassReadMaxAge = 60 * time.Second
	// ClockSkew is the accepted bounded clock skew for age and expiry checks.
	ClockSkew = 5 * time.Second
	// DefaultTTL is the issuer-side snapshot lifetime when unset.
	DefaultTTL = 60 * time.Second

	maxPayloadBytes = 16 * 1024
)

// Stable metric result labels for policy snapshot issuance/verification.
// Labels never contain org, agent, or claim content.
const (
	MetricIssued           = "issued"
	MetricDenied           = "denied"
	MetricInvalidToken     = "invalid_token"
	MetricExpired          = "expired"
	MetricOrgMismatch      = "org_mismatch"
	MetricAgentMismatch    = "agent_mismatch"
	MetricKeyUnknown       = "key_unknown"
	MetricSignatureInvalid = "signature_invalid"
	MetricUnavailable      = "unavailable"
)

// Class is the operation class that bounds accepted snapshot age.
type Class int

const (
	// ClassMutation covers mutating or externally effectful requests (30s).
	ClassMutation Class = iota
	// ClassRead covers protected reads and context assembly (60s).
	ClassRead
)

// MaxAge returns the accepted maximum age for the class.
func (c Class) MaxAge() time.Duration {
	if c == ClassRead {
		return ClassReadMaxAge
	}
	return ClassMutationMaxAge
}

// Typed verification failures. Callers map these to stable API error codes and
// must fail closed on every one of them.
var (
	// ErrMalformed indicates the envelope or claims are structurally invalid.
	ErrMalformed = errors.New("policy snapshot malformed")
	// ErrSignatureInvalid indicates the signature or claim digest did not verify.
	ErrSignatureInvalid = errors.New("policy snapshot signature invalid")
	// ErrKeyUnknown indicates the envelope key_id is not in the trusted key set.
	ErrKeyUnknown = errors.New("policy snapshot key unknown")
	// ErrExpired indicates the snapshot is expired, stale for its class, or
	// issued in the future beyond the accepted clock skew.
	ErrExpired = errors.New("policy snapshot expired or stale")
	// ErrOrgMismatch indicates the snapshot org does not match the request org.
	ErrOrgMismatch = errors.New("policy snapshot org mismatch")
	// ErrAgentMismatch indicates the snapshot agent does not match the request agent.
	ErrAgentMismatch = errors.New("policy snapshot agent mismatch")
)

// Claims is the immutable scope attested by the policy-signing authority.
// Digest covers the canonical form of the claims with Digest blanked.
type Claims struct {
	ContractVersion string `json:"contract_version"`
	Authority       string `json:"authority"`
	OrgID           string `json:"org_id"`
	SubjectID       string `json:"subject_id"`
	AgentID         string `json:"agent_id"`
	SnapshotID      string `json:"snapshot_id"`
	Epoch           int64  `json:"epoch"`
	Permissions     int64  `json:"permissions"`
	IssuedAt        int64  `json:"issued_at"`
	ExpiresAt       int64  `json:"expires_at"`
	Digest          string `json:"digest"`
}

// Envelope carries the canonical claims, their signature, and the signing key
// identity.
type Envelope struct {
	Algorithm string
	KeyID     string
	Payload   []byte
	Signature []byte
}

func (c Claims) validateStructure() error {
	if err := c.validateIdentity(); err != nil {
		return err
	}
	return c.validateScope()
}

func (c Claims) validateIdentity() error {
	switch {
	case c.ContractVersion != ContractVersion:
		return fmt.Errorf("%w: unsupported contract_version", ErrMalformed)
	case c.Authority != AuthorityAuthService:
		return fmt.Errorf("%w: unsupported authority", ErrMalformed)
	case strings.TrimSpace(c.OrgID) == "":
		return fmt.Errorf("%w: missing org_id", ErrMalformed)
	case strings.TrimSpace(c.SubjectID) == "":
		return fmt.Errorf("%w: missing subject_id", ErrMalformed)
	case strings.TrimSpace(c.SnapshotID) == "":
		return fmt.Errorf("%w: missing snapshot_id", ErrMalformed)
	default:
		return nil
	}
}

func (c Claims) validateScope() error {
	switch {
	case c.Epoch < 1:
		return fmt.Errorf("%w: invalid epoch", ErrMalformed)
	case c.Permissions < 0:
		return fmt.Errorf("%w: invalid permissions", ErrMalformed)
	case c.IssuedAt <= 0 || c.ExpiresAt <= c.IssuedAt:
		return fmt.Errorf("%w: invalid validity window", ErrMalformed)
	default:
		return nil
	}
}

func (c Claims) marshalClaims() ([]byte, error) {
	raw, err := json.Marshal(c)
	if err != nil {
		return nil, fmt.Errorf("%w: marshal claims: %v", ErrMalformed, err)
	}
	return raw, nil
}

func (c Claims) computeDigest() (string, error) {
	c.Digest = ""
	payload, err := c.canonicalPayload()
	if err != nil {
		return "", err
	}
	return hex.EncodeToString(sha256Sum(payload)), nil
}

func (c Claims) canonicalPayload() ([]byte, error) {
	raw, err := c.marshalClaims()
	if err != nil {
		return nil, err
	}
	payload, err := canonicaljson.Canonicalize(raw)
	if err != nil {
		return nil, fmt.Errorf("%w: canonicalize claims: %v", ErrMalformed, err)
	}
	return payload, nil
}

func sha256Sum(data []byte) []byte {
	sum := sha256.Sum256(data)
	return sum[:]
}
