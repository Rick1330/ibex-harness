package sessionjwt

import (
	"crypto"
	"crypto/rsa"
	"crypto/sha256"
	"crypto/x509"
	"encoding/base64"
	"encoding/json"
	"encoding/pem"
	"fmt"
	"strings"
	"time"
)

// Verifier checks RS256 JWTs against one or more PEM public keys.
type Verifier struct {
	keys     []*rsa.PublicKey
	issuer   string
	audience string
}

// VerifierConfig scopes NewVerifier construction.
type VerifierConfig struct {
	PublicKeysPEM PublicKeysPEM
	Issuer        TokenIssuer
	Audience      TokenAudience
}

// NewVerifier parses one or more PEM public keys (concatenated PEM blocks).
func NewVerifier(cfg VerifierConfig) (*Verifier, error) {
	keys, err := parseRSAPublicKeys(string(cfg.PublicKeysPEM))
	if err != nil {
		return nil, err
	}
	if len(keys) == 0 {
		return nil, fmt.Errorf("sessionjwt: no public keys")
	}
	return &Verifier{keys: keys, issuer: string(cfg.Issuer), audience: string(cfg.Audience)}, nil
}

// Verify validates signature and standard claims; expectKind must match session_kind.
func (v *Verifier) Verify(token string, expectKind SessionKind) (Claims, error) {
	parts := strings.Split(token, ".")
	if len(parts) != 3 {
		return Claims{}, ErrInvalidToken
	}
	if err := v.verifySignature(parts[0], parts[1], parts[2]); err != nil {
		return Claims{}, err
	}
	return v.parseAndValidateClaims(parts[1], string(expectKind))
}

func (v *Verifier) verifySignature(headerB64, payloadB64, sigB64 string) error {
	sig, err := b64dec(sigB64)
	if err != nil {
		return ErrInvalidToken
	}
	body := headerB64 + "." + payloadB64
	sum := sha256.Sum256([]byte(body))
	for _, key := range v.keys {
		// JWT RS256 (RFC 7518) requires PKCS#1 v1.5 verification.
		if rsa.VerifyPKCS1v15(key, crypto.SHA256, sum[:], sig) == nil { // NOSONAR
			return nil
		}
	}
	return ErrInvalidToken
}

func (v *Verifier) parseAndValidateClaims(payloadB64, expectKind string) (Claims, error) {
	raw, err := b64dec(payloadB64)
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
