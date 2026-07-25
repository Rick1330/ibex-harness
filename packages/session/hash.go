package session

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
)

// MessageForHash is the role/content pair hashed into messages_hash.
type MessageForHash struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

// HashMessages returns the SHA-256 hex digest of the canonical JSON messages array.
func HashMessages(msgs []MessageForHash) string {
	payload, err := json.Marshal(msgs)
	if err != nil {
		return HashText("")
	}
	return HashBytes(payload)
}

// HashText returns the SHA-256 hex digest of s.
func HashText(s string) string {
	return HashBytes([]byte(s))
}

// HashBytes returns the SHA-256 hex digest of b.
func HashBytes(b []byte) string {
	sum := sha256.Sum256(b)
	return hex.EncodeToString(sum[:])
}
