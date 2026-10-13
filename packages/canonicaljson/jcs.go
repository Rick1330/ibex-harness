package canonicaljson

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"

	jsoncanonicalizer "github.com/cyberphone/json-canonicalization/go/src/webpki.org/jsoncanonicalizer"
)

// Canonicalize returns RFC 8785-compatible canonical UTF-8 JSON bytes.
// The input must be one complete JSON value; duplicate object names and
// malformed JSON are rejected by the vetted canonicalizer.
func Canonicalize(input []byte) ([]byte, error) {
	canonical, err := jsoncanonicalizer.Transform(input)
	if err != nil {
		return nil, fmt.Errorf("canonicaljson: canonicalize: %w", err)
	}
	return canonical, nil
}

// Digest returns the lowercase SHA-256 digest of canonical JSON bytes.
func Digest(input []byte) (canonical []byte, digest string, err error) {
	canonical, err = Canonicalize(input)
	if err != nil {
		return nil, "", err
	}
	sum := sha256.Sum256(canonical)
	return canonical, hex.EncodeToString(sum[:]), nil
}
