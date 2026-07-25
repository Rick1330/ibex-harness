package session

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
)

// MessageForHash is the role/content pair hashed into messages_hash.
// Only role and content are included so hashes stay stable across optional
// provider fields that are not persisted in Phase 2 checkpoints (ADR-0032).
type MessageForHash struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

// HashMessages returns the SHA-256 hex digest of the canonical JSON encoding of
// msgs (encoding/json map key order is deterministic for this struct). On
// marshal failure it falls back to HashText("") so callers always get a digest.
func HashMessages(msgs []MessageForHash) string {
	payload, err := json.Marshal(msgs)
	if err != nil {
		return HashText("")
	}
	return HashBytes(payload)
}

// HashText returns the SHA-256 hex digest of s (completion_hash / empty fallback).
func HashText(s string) string {
	return HashBytes([]byte(s))
}

// HashBytes returns the SHA-256 hex digest of b without additional encoding.
func HashBytes(b []byte) string {
	sum := sha256.Sum256(b)
	return hex.EncodeToString(sum[:])
}
