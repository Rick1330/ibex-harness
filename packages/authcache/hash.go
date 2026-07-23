package authcache

import (
	"crypto/sha256"
	"encoding/hex"
)

// TokenHash returns the SHA-256 hex digest of token. Shared with 2.2.2 invalidate events.
func TokenHash(token string) string {
	sum := sha256.Sum256([]byte(token))
	return hex.EncodeToString(sum[:])
}
