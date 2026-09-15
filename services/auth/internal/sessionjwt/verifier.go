package sessionjwt

import (
	"crypto/rsa"
	"encoding/json"
	"fmt"
	"strings"
	"time"
)

// Verifier checks RS256 JWTs against one or more PEM public keys.
type Verifier struct {
	keys     []*rsa.PublicKey
	issuer   TokenIssuer
	audience TokenAudience
}

// VerifierConfig scopes NewVerifier construction.
type VerifierConfig struct {
	PublicKeysPEM PublicKeysPEM
	Issuer        TokenIssuer
	Audience      TokenAudience
}

type jwtWireParts struct {
	header  string
	payload string
	sig     string
}

// NewVerifier parses one or more PEM public keys (concatenated PEM blocks).
func NewVerifier(cfg VerifierConfig) (*Verifier, error) {
	keys, err := parseRSAPublicKeys(cfg.PublicKeysPEM)
	if err != nil {
		return nil, err
	}
	if len(keys) == 0 {
		return nil, fmt.Errorf("sessionjwt: no public keys")
	}
	return &Verifier{keys: keys, issuer: cfg.Issuer, audience: cfg.Audience}, nil
}

// Verify validates signature and standard claims; expectKind must match session_kind.
func (v *Verifier) Verify(token RawToken, expectKind SessionKind) (Claims, error) {
	parts, err := splitJWT(string(token))
	if err != nil {
		return Claims{}, err
	}
	if err := v.verifySignature(parts); err != nil {
		return Claims{}, err
	}
	return v.parseAndValidateClaims(parts.payload, expectKind)
}

func splitJWT(token string) (jwtWireParts, error) {
	parts := strings.Split(token, ".")
	if len(parts) != 3 {
		return jwtWireParts{}, ErrInvalidToken
	}
	return jwtWireParts{header: parts[0], payload: parts[1], sig: parts[2]}, nil
}

func (v *Verifier) verifySignature(parts jwtWireParts) error {
	sig, err := b64dec(parts.sig)
	if err != nil {
		return ErrInvalidToken
	}
	sum := sha256Sum(parts.header + "." + parts.payload)
	for _, key := range v.keys {
		if verifyPKCS1(key, sum[:], sig) == nil {
			return nil
		}
	}
	return ErrInvalidToken
}

func (v *Verifier) parseAndValidateClaims(payloadB64 string, expectKind SessionKind) (Claims, error) {
	raw, err := b64dec(payloadB64)
	if err != nil {
		return Claims{}, ErrInvalidToken
	}
	var claims Claims
	if err := json.Unmarshal(raw, &claims); err != nil {
		return Claims{}, ErrInvalidToken
	}
	if claims.Issuer != string(v.issuer) || claims.Audience != string(v.audience) {
		return Claims{}, ErrInvalidToken
	}
	if claims.SessionKind != string(expectKind) {
		return Claims{}, ErrInvalidToken
	}
	if claims.ExpiresAt < time.Now().UTC().Unix() {
		return Claims{}, ErrExpired
	}
	return claims, nil
}
