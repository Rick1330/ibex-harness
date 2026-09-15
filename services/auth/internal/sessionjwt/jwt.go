// Package sessionjwt issues and verifies operator session JWTs (stdlib RSA + JSON).
package sessionjwt

import (
	"context"
	"crypto"
	"crypto/rand"
	"crypto/rsa"
	"crypto/sha256"
	"encoding/json"
	"errors"
	"strings"
	"time"

	"github.com/google/uuid"
)

// Typed config fields reduce primitive string coupling for Code Health.
type PrivateKeyPEM string
type TokenIssuer string
type TokenAudience string
type Subject string
type OrgID string
type FamilyID string
type RefreshToken string
type PublicKeysPEM string
type SessionKind string
type RawToken string

const (
	KindAccess  SessionKind = "access"
	KindRefresh SessionKind = "refresh"
	KindStepUp  SessionKind = "step_up"
	algRS256                = "RS256"
)

var (
	ErrInvalidToken = errors.New("sessionjwt: invalid token")
	ErrExpired      = errors.New("sessionjwt: expired")
)

// Claims mirrors services/api SessionClaims (+ optional step-up marker / refresh family).
type Claims struct {
	Issuer      string `json:"iss"`
	Audience    string `json:"aud"`
	Subject     string `json:"sub"`
	OrgID       string `json:"org_id"`
	Permissions int64  `json:"permissions"`
	SessionKind string `json:"session_kind"`
	IssuedAt    int64  `json:"iat"`
	ExpiresAt   int64  `json:"exp"`
	JTI         string `json:"jti"`
	FamilyID    string `json:"fid,omitempty"`
}

// IssuerConfig holds RS256 signing material and token TTLs for NewIssuer.
type IssuerConfig struct {
	PrivateKeyPEM PrivateKeyPEM
	Issuer        TokenIssuer
	Audience      TokenAudience
	AccessTTL     time.Duration
	RefreshTTL    time.Duration
	StepUpTTL     time.Duration
}

// Issuer signs RS256 JWTs with a PEM private key.
type Issuer struct {
	key        *rsa.PrivateKey
	issuer     string
	audience   string
	accessTTL  time.Duration
	refreshTTL time.Duration
	stepUpTTL  time.Duration
	jtiStore   JTIStore
}

// NewIssuer parses PKCS1/PKCS8 RSA private key PEM.
func NewIssuer(cfg IssuerConfig) (*Issuer, error) {
	key, err := parseRSAPrivateKey(cfg.PrivateKeyPEM)
	if err != nil {
		return nil, err
	}
	return &Issuer{
		key: key, issuer: string(cfg.Issuer), audience: string(cfg.Audience),
		accessTTL:  defaultTTL(cfg.AccessTTL, 15*time.Minute),
		refreshTTL: defaultTTL(cfg.RefreshTTL, 7*24*time.Hour),
		stepUpTTL:  defaultTTL(cfg.StepUpTTL, 5*time.Minute),
		jtiStore:   &MemoryJTIStore{},
	}, nil
}

func defaultTTL(got, fallback time.Duration) time.Duration {
	if got <= 0 {
		return fallback
	}
	return got
}

// WithJTIStore replaces the refresh JTI consumer (Redis in production).
func (i *Issuer) WithJTIStore(store JTIStore) *Issuer {
	if i == nil || store == nil {
		return i
	}
	i.jtiStore = store
	return i
}

// IssuePairParams scopes access+refresh issuance.
type IssuePairParams struct {
	Subject     Subject
	OrgID       OrgID
	Permissions int64
	// FamilyID binds rotated refresh tokens; empty mints a new family.
	FamilyID FamilyID
}

// IssuePair returns access + refresh tokens for an operator session.
func (i *Issuer) IssuePair(p IssuePairParams) (access, refresh string, accessExp, refreshExp time.Time, err error) {
	now := time.Now().UTC()
	accessExp = now.Add(i.accessTTL)
	refreshExp = now.Add(i.refreshTTL)
	familyID := strings.TrimSpace(string(p.FamilyID))
	if familyID == "" {
		familyID = uuid.NewString()
	}
	access, err = i.sign(Claims{
		Issuer: i.issuer, Audience: i.audience, Subject: string(p.Subject), OrgID: string(p.OrgID),
		Permissions: p.Permissions, SessionKind: string(KindAccess),
		IssuedAt: now.Unix(), ExpiresAt: accessExp.Unix(), JTI: uuid.NewString(),
	})
	if err != nil {
		return "", "", time.Time{}, time.Time{}, err
	}
	refresh, err = i.sign(Claims{
		Issuer: i.issuer, Audience: i.audience, Subject: string(p.Subject), OrgID: string(p.OrgID),
		Permissions: p.Permissions, SessionKind: string(KindRefresh), FamilyID: familyID,
		IssuedAt: now.Unix(), ExpiresAt: refreshExp.Unix(), JTI: uuid.NewString(),
	})
	if err != nil {
		return "", "", time.Time{}, time.Time{}, err
	}
	return access, refresh, accessExp, refreshExp, nil
}

// IssueStepUpParams scopes step-up JWT issuance.
type IssueStepUpParams struct {
	Subject     Subject
	OrgID       OrgID
	Permissions int64
}

// IssueStepUp returns a short-lived step-up token after TOTP verification.
func (i *Issuer) IssueStepUp(p IssueStepUpParams) (token string, exp time.Time, err error) {
	now := time.Now().UTC()
	exp = now.Add(i.stepUpTTL)
	token, err = i.sign(Claims{
		Issuer: i.issuer, Audience: i.audience, Subject: string(p.Subject), OrgID: string(p.OrgID),
		Permissions: p.Permissions, SessionKind: string(KindStepUp),
		IssuedAt: now.Unix(), ExpiresAt: exp.Unix(), JTI: uuid.NewString(),
	})
	return token, exp, err
}

// RefreshPair verifies a refresh JWT with the issuer's public key and rotates the pair.
// The refresh JTI is consumed atomically via JTIStore; reuse revokes the whole family.
func (i *Issuer) RefreshPair(ctx context.Context, refreshToken RefreshToken) (access, refresh string, accessExp, refreshExp time.Time, err error) {
	claims, err := i.verifyRefreshToken(refreshToken)
	if err != nil {
		return "", "", time.Time{}, time.Time{}, err
	}
	if err := i.consumeRefreshOrRevoke(ctx, claims); err != nil {
		return "", "", time.Time{}, time.Time{}, err
	}
	return i.IssuePair(IssuePairParams{
		Subject: Subject(claims.Subject), OrgID: OrgID(claims.OrgID), Permissions: claims.Permissions,
		FamilyID: FamilyID(claims.FamilyID),
	})
}

func (i *Issuer) verifyRefreshToken(refreshToken RefreshToken) (Claims, error) {
	v := &Verifier{
		keys:     []*rsa.PublicKey{&i.key.PublicKey},
		issuer:   TokenIssuer(i.issuer),
		audience: TokenAudience(i.audience),
	}
	claims, err := v.Verify(RawToken(refreshToken), KindRefresh)
	if err != nil {
		return Claims{}, err
	}
	if err := validateRefreshClaims(claims); err != nil {
		return Claims{}, err
	}
	return claims, nil
}

func (i *Issuer) consumeRefreshOrRevoke(ctx context.Context, claims Claims) error {
	ttl := refreshRemainingTTL(claims)
	revoked, err := i.jtiStore.FamilyRevoked(ctx, claims.FamilyID)
	if err != nil {
		return err
	}
	if revoked {
		return ErrInvalidToken
	}
	first, err := i.jtiStore.ConsumeOnce(ctx, claims.JTI, ttl)
	if err != nil {
		return err
	}
	if first {
		return nil
	}
	familyTTL := i.refreshTTL
	if ttl > familyTTL {
		familyTTL = ttl
	}
	_ = i.jtiStore.RevokeFamily(ctx, claims.FamilyID, familyTTL)
	return ErrInvalidToken
}

func refreshRemainingTTL(claims Claims) time.Duration {
	ttl := time.Until(time.Unix(claims.ExpiresAt, 0).UTC())
	if ttl <= 0 {
		return time.Second
	}
	return ttl
}

func validateRefreshClaims(claims Claims) error {
	if claims.Subject == "" {
		return ErrInvalidToken
	}
	if claims.OrgID == "" {
		return ErrInvalidToken
	}
	if claims.JTI == "" {
		return ErrInvalidToken
	}
	if claims.FamilyID == "" {
		return ErrInvalidToken
	}
	return nil
}

func (i *Issuer) sign(claims Claims) (string, error) {
	header := map[string]string{"alg": algRS256, "typ": "JWT"}
	hb, err := json.Marshal(header)
	if err != nil {
		return "", err
	}
	pb, err := json.Marshal(claims)
	if err != nil {
		return "", err
	}
	body := b64(hb) + "." + b64(pb)
	sum := sha256.Sum256([]byte(body))
	// JWT RS256 (RFC 7518) requires PKCS#1 v1.5 signatures, not OAEP/PSS.
	sig, err := rsa.SignPKCS1v15(rand.Reader, i.key, crypto.SHA256, sum[:]) // NOSONAR
	if err != nil {
		return "", err
	}
	return body + "." + b64(sig), nil
}
