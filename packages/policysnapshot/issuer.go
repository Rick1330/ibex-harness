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
	key, err := parseSigningKey(cfg.PrivateKeyPEM)
	if err != nil {
		return nil, err
	}
	keyID, err := resolveKeyID(cfg.KeyID)
	if err != nil {
		return nil, err
	}
	epoch, err := resolveEpoch(cfg.Epoch)
	if err != nil {
		return nil, err
	}
	authority, err := resolveAuthority(cfg.Authority)
	if err != nil {
		return nil, err
	}
	ttl, err := resolveTTL(cfg.TTL)
	if err != nil {
		return nil, err
	}
	return &Issuer{
		key: key, keyID: keyID, epoch: epoch, authority: authority,
		ttl: ttl, clock: resolveClock(cfg.Clock), newID: resolveNewID(cfg.NewID),
	}, nil
}

func parseSigningKey(pemData string) (*rsa.PrivateKey, error) {
	key, err := parsePrivateKeyPEM(pemData)
	if err != nil {
		return nil, err
	}
	if key.N.BitLen() < minRSAKeyBits {
		return nil, fmt.Errorf("policysnapshot: signing key must be >= %d bits", minRSAKeyBits)
	}
	return key, nil
}

func resolveKeyID(raw string) (string, error) {
	keyID := strings.TrimSpace(raw)
	if keyID == "" {
		return "", fmt.Errorf("policysnapshot: empty key id")
	}
	return keyID, nil
}

func resolveEpoch(epoch int64) (int64, error) {
	if epoch < 1 {
		return 0, fmt.Errorf("policysnapshot: epoch must be >= 1")
	}
	return epoch, nil
}

func resolveAuthority(raw string) (string, error) {
	authority := strings.TrimSpace(raw)
	if authority == "" {
		authority = AuthorityAuthService
	}
	if authority != AuthorityAuthService {
		return "", fmt.Errorf("policysnapshot: unsupported authority %q", authority)
	}
	return authority, nil
}

func resolveTTL(ttl time.Duration) (time.Duration, error) {
	if ttl == 0 {
		ttl = DefaultTTL
	}
	if ttl < time.Second {
		return 0, fmt.Errorf("policysnapshot: ttl must be >= 1s")
	}
	return ttl, nil
}

func resolveClock(clock func() time.Time) func() time.Time {
	if clock == nil {
		return func() time.Time { return time.Now().UTC() }
	}
	return clock
}

func resolveNewID(newID func() string) func() string {
	if newID == nil {
		return uuid.NewString
	}
	return newID
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
	// RS256 pins PKCS#1 v1.5 signature padding per the G0 owner decision
	// record (21-g0-owner-decision-record.md §2.1); this is signature
	// padding, not encryption.
	signature, err := rsa.SignPKCS1v15(rand.Reader, i.key, crypto.SHA256, sha256Sum(payload)) //NOSONAR go:S5542 RS256 requires PKCS#1 v1.5 signature padding
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
