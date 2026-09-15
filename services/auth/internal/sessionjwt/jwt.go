// Package sessionjwt issues and verifies operator session JWTs (stdlib RSA + JSON).
package sessionjwt

import (
	"crypto"
	"crypto/rand"
	"crypto/rsa"
	"crypto/sha256"
	"crypto/x509"
	"encoding/base64"
	"encoding/json"
	"encoding/pem"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/google/uuid"
)

const (
	KindAccess  = "access"
	KindRefresh = "refresh"
	KindStepUp  = "step_up"
	algRS256    = "RS256"
)

var (
	ErrInvalidToken = errors.New("sessionjwt: invalid token")
	ErrExpired      = errors.New("sessionjwt: expired")
)

// Claims mirrors services/api SessionClaims (+ optional step-up marker).
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
}

// Issuer signs RS256 JWTs with a PEM private key.
type Issuer struct {
	key        *rsa.PrivateKey
	issuer     string
	audience   string
	accessTTL  time.Duration
	refreshTTL time.Duration
	stepUpTTL  time.Duration
}

// NewIssuer parses PKCS1/PKCS8 RSA private key PEM.
func NewIssuer(privateKeyPEM, issuer, audience string, accessTTL, refreshTTL, stepUpTTL time.Duration) (*Issuer, error) {
	key, err := parseRSAPrivateKey(privateKeyPEM)
	if err != nil {
		return nil, err
	}
	if accessTTL <= 0 {
		accessTTL = 15 * time.Minute
	}
	if refreshTTL <= 0 {
		refreshTTL = 7 * 24 * time.Hour
	}
	if stepUpTTL <= 0 {
		stepUpTTL = 5 * time.Minute
	}
	return &Issuer{
		key: key, issuer: issuer, audience: audience,
		accessTTL: accessTTL, refreshTTL: refreshTTL, stepUpTTL: stepUpTTL,
	}, nil
}

// IssuePair returns access + refresh tokens for an operator session.
func (i *Issuer) IssuePair(sub, orgID string, permissions int64) (access, refresh string, accessExp, refreshExp time.Time, err error) {
	now := time.Now().UTC()
	accessExp = now.Add(i.accessTTL)
	refreshExp = now.Add(i.refreshTTL)
	access, err = i.sign(Claims{
		Issuer: i.issuer, Audience: i.audience, Subject: sub, OrgID: orgID,
		Permissions: permissions, SessionKind: KindAccess,
		IssuedAt: now.Unix(), ExpiresAt: accessExp.Unix(), JTI: uuid.NewString(),
	})
	if err != nil {
		return "", "", time.Time{}, time.Time{}, err
	}
	refresh, err = i.sign(Claims{
		Issuer: i.issuer, Audience: i.audience, Subject: sub, OrgID: orgID,
		Permissions: permissions, SessionKind: KindRefresh,
		IssuedAt: now.Unix(), ExpiresAt: refreshExp.Unix(), JTI: uuid.NewString(),
	})
	if err != nil {
		return "", "", time.Time{}, time.Time{}, err
	}
	return access, refresh, accessExp, refreshExp, nil
}

// IssueStepUp returns a short-lived step-up token after TOTP verification.
func (i *Issuer) IssueStepUp(sub, orgID string, permissions int64) (token string, exp time.Time, err error) {
	now := time.Now().UTC()
	exp = now.Add(i.stepUpTTL)
	token, err = i.sign(Claims{
		Issuer: i.issuer, Audience: i.audience, Subject: sub, OrgID: orgID,
		Permissions: permissions, SessionKind: KindStepUp,
		IssuedAt: now.Unix(), ExpiresAt: exp.Unix(), JTI: uuid.NewString(),
	})
	return token, exp, err
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

// Verifier checks RS256 JWTs against one or more PEM public keys.
type Verifier struct {
	keys     []*rsa.PublicKey
	issuer   string
	audience string
}

// NewVerifier parses one or more PEM public keys (concatenated PEM blocks).
func NewVerifier(publicKeysPEM, issuer, audience string) (*Verifier, error) {
	keys, err := parseRSAPublicKeys(publicKeysPEM)
	if err != nil {
		return nil, err
	}
	if len(keys) == 0 {
		return nil, fmt.Errorf("sessionjwt: no public keys")
	}
	return &Verifier{keys: keys, issuer: issuer, audience: audience}, nil
}

// Verify validates signature and standard claims; expectKind must match session_kind.
func (v *Verifier) Verify(token, expectKind string) (Claims, error) {
	parts := strings.Split(token, ".")
	if len(parts) != 3 {
		return Claims{}, ErrInvalidToken
	}
	sig, err := b64dec(parts[2])
	if err != nil {
		return Claims{}, ErrInvalidToken
	}
	body := parts[0] + "." + parts[1]
	sum := sha256.Sum256([]byte(body))
	ok := false
	for _, key := range v.keys {
		// JWT RS256 (RFC 7518) requires PKCS#1 v1.5 verification.
		if rsa.VerifyPKCS1v15(key, crypto.SHA256, sum[:], sig) == nil { // NOSONAR
			ok = true
			break
		}
	}
	if !ok {
		return Claims{}, ErrInvalidToken
	}
	raw, err := b64dec(parts[1])
	if err != nil {
		return Claims{}, ErrInvalidToken
	}
	var claims Claims
	if err := json.Unmarshal(raw, &claims); err != nil {
		return Claims{}, ErrInvalidToken
	}
	if claims.Issuer != v.issuer || claims.Audience != v.audience {
		return Claims{}, ErrInvalidToken
	}
	if claims.SessionKind != expectKind {
		return Claims{}, ErrInvalidToken
	}
	if claims.ExpiresAt < time.Now().UTC().Unix() {
		return Claims{}, ErrExpired
	}
	return claims, nil
}

func parseRSAPrivateKey(pemData string) (*rsa.PrivateKey, error) {
	block, _ := pem.Decode([]byte(pemData))
	if block == nil {
		return nil, fmt.Errorf("sessionjwt: invalid private key pem")
	}
	if key, err := x509.ParsePKCS1PrivateKey(block.Bytes); err == nil {
		return key, nil
	}
	parsed, err := x509.ParsePKCS8PrivateKey(block.Bytes)
	if err != nil {
		return nil, fmt.Errorf("sessionjwt: parse private key: %w", err)
	}
	key, ok := parsed.(*rsa.PrivateKey)
	if !ok {
		return nil, fmt.Errorf("sessionjwt: not an RSA private key")
	}
	return key, nil
}

func parseRSAPublicKeys(pemData string) ([]*rsa.PublicKey, error) {
	var keys []*rsa.PublicKey
	rest := []byte(pemData)
	for {
		var block *pem.Block
		block, rest = pem.Decode(rest)
		if block == nil {
			break
		}
		key, err := parseRSAPublicKeyBlock(block)
		if err != nil {
			return nil, err
		}
		if key != nil {
			keys = append(keys, key)
		}
	}
	return keys, nil
}

func parseRSAPublicKeyBlock(block *pem.Block) (*rsa.PublicKey, error) {
	pub, err := x509.ParsePKIXPublicKey(block.Bytes)
	if err == nil {
		rsaPub, ok := pub.(*rsa.PublicKey)
		if !ok {
			return nil, fmt.Errorf("sessionjwt: not an RSA public key")
		}
		return rsaPub, nil
	}
	cert, cerr := x509.ParseCertificate(block.Bytes)
	if cerr != nil {
		return nil, fmt.Errorf("sessionjwt: parse public key: %w", err)
	}
	rsaPub, ok := cert.PublicKey.(*rsa.PublicKey)
	if !ok {
		return nil, nil
	}
	return rsaPub, nil
}

func b64(b []byte) string {
	return base64.RawURLEncoding.EncodeToString(b)
}

func b64dec(s string) ([]byte, error) {
	return base64.RawURLEncoding.DecodeString(s)
}
