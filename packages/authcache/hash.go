package authcache

import (
	"crypto/sha256"
	"encoding/hex"
)

// digest is a SHA-256 hex token key (never the raw bearer token).
type digest string

// TokenHash returns the SHA-256 hex digest of token. Shared with 2.2.2 invalidate events.
func TokenHash(token string) string {
	return string(hashToken(token))
}

func hashToken(token string) digest {
	sum := sha256.Sum256([]byte(token))
	return digest(hex.EncodeToString(sum[:]))
}

func digestFromHex(tokenHash string) digest {
	return digest(tokenHash)
}
