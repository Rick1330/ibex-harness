package policysnapshot

import (
	"crypto/rsa"
	"crypto/x509"
	"encoding/json"
	"encoding/pem"
	"fmt"
	"sort"
	"strings"
)

// KeySet is an authority-owned set of policy-signing public keys, keyed by
// key_id. Rotation publishes a new key id before issuing with it and keeps the
// previous key until the maximum accepted snapshot age plus clock skew has
// passed.
type KeySet struct {
	keys map[string]*rsa.PublicKey
}

// NewKeySet builds a key set from parsed public keys. It rejects empty ids,
// nil keys, and an empty set.
func NewKeySet(keys map[string]*rsa.PublicKey) (KeySet, error) {
	if len(keys) == 0 {
		return KeySet{}, fmt.Errorf("policysnapshot: empty key set")
	}
	out := make(map[string]*rsa.PublicKey, len(keys))
	for id, key := range keys {
		trimmed := strings.TrimSpace(id)
		if trimmed == "" {
			return KeySet{}, fmt.Errorf("policysnapshot: empty key id")
		}
		if key == nil {
			return KeySet{}, fmt.Errorf("policysnapshot: nil public key for %q", trimmed)
		}
		out[trimmed] = key
	}
	return KeySet{keys: out}, nil
}

// ParseKeySetJSON parses a JSON object of key_id -> PEM-encoded RSA public key.
// The raw value comes from configuration, never from a caller.
func ParseKeySetJSON(raw string) (KeySet, error) {
	if strings.TrimSpace(raw) == "" {
		return KeySet{}, fmt.Errorf("policysnapshot: empty key set JSON")
	}
	decoded := map[string]string{}
	if err := json.Unmarshal([]byte(raw), &decoded); err != nil {
		return KeySet{}, fmt.Errorf("policysnapshot: key set JSON: %w", err)
	}
	keys := make(map[string]*rsa.PublicKey, len(decoded))
	for id, pemData := range decoded {
		key, err := ParsePublicKeyPEM(pemData)
		if err != nil {
			return KeySet{}, fmt.Errorf("policysnapshot: key %q: %w", strings.TrimSpace(id), err)
		}
		keys[id] = key
	}
	return NewKeySet(keys)
}

// ParsePublicKeyPEM parses one PEM block holding an RSA public key (PKIX) or
// certificate.
func ParsePublicKeyPEM(pemData string) (*rsa.PublicKey, error) {
	block, _ := pem.Decode([]byte(pemData))
	if block == nil {
		return nil, fmt.Errorf("policysnapshot: invalid public key pem")
	}
	if pub, err := x509.ParsePKIXPublicKey(block.Bytes); err == nil {
		rsaPub, ok := pub.(*rsa.PublicKey)
		if !ok {
			return nil, fmt.Errorf("policysnapshot: not an RSA public key")
		}
		return rsaPub, nil
	}
	cert, err := x509.ParseCertificate(block.Bytes)
	if err != nil {
		return nil, fmt.Errorf("policysnapshot: parse public key: %w", err)
	}
	rsaPub, ok := cert.PublicKey.(*rsa.PublicKey)
	if !ok {
		return nil, fmt.Errorf("policysnapshot: certificate does not hold an RSA key")
	}
	return rsaPub, nil
}

// Lookup returns the public key for key_id.
func (k KeySet) Lookup(keyID string) (*rsa.PublicKey, bool) {
	key, ok := k.keys[keyID]
	return key, ok
}

// KeyIDs returns the sorted key ids for diagnostics (never log key material).
func (k KeySet) KeyIDs() []string {
	ids := make([]string, 0, len(k.keys))
	for id := range k.keys {
		ids = append(ids, id)
	}
	sort.Strings(ids)
	return ids
}

func parsePrivateKeyPEM(pemData string) (*rsa.PrivateKey, error) {
	block, _ := pem.Decode([]byte(pemData))
	if block == nil {
		return nil, fmt.Errorf("policysnapshot: invalid private key pem")
	}
	if key, err := x509.ParsePKCS1PrivateKey(block.Bytes); err == nil {
		return key, nil
	}
	parsed, err := x509.ParsePKCS8PrivateKey(block.Bytes)
	if err != nil {
		return nil, fmt.Errorf("policysnapshot: parse private key: %w", err)
	}
	key, ok := parsed.(*rsa.PrivateKey)
	if !ok {
		return nil, fmt.Errorf("policysnapshot: not an RSA private key")
	}
	return key, nil
}
