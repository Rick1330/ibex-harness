package policysnapshot

import (
	"crypto"
	"crypto/rand"
	"crypto/rsa"
	"fmt"
	"strings"
	"time"

	"github.com/google/uuid"
)

const minRSAKeyBits = 2048

// IssuerConfig configures the policy-signing authority.
type IssuerConfig struct {
	// PrivateKeyPEM is the RSA private key (PKCS#1 or PKCS#8 PEM).
	PrivateKeyPEM string
	// KeyID names the signing key; rotation publishes a new id first.
	KeyID string
	// Epoch is the effective policy epoch; it must be >= 1 and monotonic
	// across rotations.
	Epoch int64
	// Authority defaults to AuthorityAuthService.
	Authority string
	// TTL is the snapshot lifetime; defaults to DefaultTTL.
	TTL time.Duration
	// Clock is injectable for deterministic tests.
	Clock func() time.Time
	// NewID is injectable for deterministic tests.
	NewID func() string
}

// Issuer mints signed policy snapshots.
type Issuer struct {
	key       *rsa.PrivateKey
	keyID     string
	epoch     int64
	authority string
	ttl       time.Duration
	clock     func() time.Time
	newID     func() string
}

// NewIssuer validates the signing material and configuration.
func NewIssuer(cfg IssuerConfig) (*Issuer, error) {
	key, err := parsePrivateKeyPEM(cfg.PrivateKeyPEM)
	if err != nil {
		return nil, err
	}
	if key.N.BitLen() < minRSAKeyBits {
		return nil, fmt.Errorf("policysnapshot: signing key must be >= %d bits", minRSAKeyBits)
	}
	keyID := strings.TrimSpace(cfg.KeyID)
	if keyID == "" {
		return nil, fmt.Errorf("policysnapshot: empty key id")
	}
	if cfg.Epoch < 1 {
		return nil, fmt.Errorf("policysnapshot: epoch must be >= 1")
	}
	authority := strings.TrimSpace(cfg.Authority)
	if authority == "" {
		authority = AuthorityAuthService
	}
	if authority != AuthorityAuthService {
		return nil, fmt.Errorf("policysnapshot: unsupported authority %q", authority)
	}
	ttl := cfg.TTL
	if ttl == 0 {
		ttl = DefaultTTL
	}
	if ttl < time.Second {
		return nil, fmt.Errorf("policysnapshot: ttl must be >= 1s")
	}
	clock := cfg.Clock
	if clock == nil {
		clock = func() time.Time { return time.Now().UTC() }
	}
	newID := cfg.NewID
	if newID == nil {
		newID = uuid.NewString
	}
	return &Issuer{
		key: key, keyID: keyID, epoch: cfg.Epoch, authority: authority,
		ttl: ttl, clock: clock, newID: newID,
	}, nil
}

// IssueParams is the verified caller scope to attest.
type IssueParams struct {
	OrgID       string
	SubjectID   string
	AgentID     string
	Permissions int64
}

// Issue mints an immutable signed envelope for the given scope.
func (i *Issuer) Issue(p IssueParams) (Envelope, error) {
	now := i.clock().UTC()
	claims := Claims{
		ContractVersion: ContractVersion,
		Authority:       i.authority,
		OrgID:           strings.TrimSpace(p.OrgID),
		SubjectID:       strings.TrimSpace(p.SubjectID),
		AgentID:         strings.TrimSpace(p.AgentID),
		SnapshotID:      i.newID(),
		Epoch:           i.epoch,
		Permissions:     p.Permissions,
		IssuedAt:        now.Unix(),
		ExpiresAt:       now.Add(i.ttl).Unix(),
	}
	if err := claims.validateStructure(); err != nil {
		return Envelope{}, err
	}
	digest, err := claims.computeDigest()
	if err != nil {
		return Envelope{}, err
	}
	claims.Digest = digest
	payload, err := claims.canonicalPayload()
	if err != nil {
		return Envelope{}, err
	}
	signature, err := rsa.SignPKCS1v15(rand.Reader, i.key, crypto.SHA256, sha256Sum(payload))
	if err != nil {
		return Envelope{}, fmt.Errorf("policysnapshot: sign: %w", err)
	}
	return Envelope{
		Algorithm: AlgorithmRS256,
		KeyID:     i.keyID,
		Payload:   payload,
		Signature: signature,
	}, nil
}

// Epoch returns the issuer's effective policy epoch.
func (i *Issuer) Epoch() int64 { return i.epoch }

// KeyID returns the issuer's signing key identity.
func (i *Issuer) KeyID() string { return i.keyID }
