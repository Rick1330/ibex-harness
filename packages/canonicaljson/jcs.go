package canonicaljson

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"

	jsoncanonicalizer "github.com/cyberphone/json-canonicalization/go/src/webpki.org/jsoncanonicalizer"
)

// Canonicalize returns RFC 8785-compatible canonical UTF-8 JSON bytes.
// The input must be one complete JSON value. JSON syntax is checked here;
// duplicate object names are rejected by the vetted canonicalizer.
func Canonicalize(input []byte) ([]byte, error) {
	if !json.Valid(input) {
		return nil, fmt.Errorf("canonicaljson: input is not valid JSON")
	}

	// The dependency accepts object and array roots, so wrap scalar roots in a
	// single-element array and remove that wrapper after canonicalization.
	transformInput := input
	unwrapArray := false
	root := bytes.TrimSpace(input)
	if root[0] != '{' && root[0] != '[' {
		transformInput = make([]byte, 0, len(input)+2)
		transformInput = append(transformInput, '[')
		transformInput = append(transformInput, input...)
		transformInput = append(transformInput, ']')
		unwrapArray = true
	}

	canonical, err := jsoncanonicalizer.Transform(transformInput)
	if err != nil {
		return nil, fmt.Errorf("canonicaljson: canonicalize: %w", err)
	}
	if unwrapArray {
		canonical = canonical[1 : len(canonical)-1]
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
