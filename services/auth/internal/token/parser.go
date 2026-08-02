package token

import (
	"strings"

	"github.com/google/uuid"
)

const patWirePrefix = "ibex_pat_"

// maxPATLen bounds wire PAT size to reject attacker-controlled oversized secrets
// before miss-path Argon2 (equalizeMiss) allocates on the bearer. Generated PATs
// are ~89 bytes (prefix + UUID + '_' + 43-char base64url of 32 secret bytes).
const maxPATLen = 128

// ParsedPAT holds a parsed personal access token wire value.
type ParsedPAT struct {
	Bearer string // full access_token value
	Prefix string // ibex_pat_<uuid> for DB lookup
}

// ParsePAT parses ibex_pat_<token_uuid>_<secret>.
func ParsePAT(accessToken string) (ParsedPAT, error) {
	normalized, err := normalizePATWire(accessToken)
	if err != nil {
		return ParsedPAT{}, err
	}
	return parseNormalizedPAT(normalized)
}

func normalizePATWire(accessToken string) (string, error) {
	// Bound raw wire size before TrimSpace so padding cannot bypass maxPATLen
	// or force a large trim scan.
	if accessToken == "" || len(accessToken) > maxPATLen {
		return "", ErrUnauthenticated
	}
	accessToken = strings.TrimSpace(accessToken)
	if accessToken == "" {
		return "", ErrUnauthenticated
	}
	return accessToken, nil
}

func parseNormalizedPAT(accessToken string) (ParsedPAT, error) {
	if !strings.HasPrefix(accessToken, patWirePrefix) {
		return ParsedPAT{}, ErrUnauthenticated
	}
	uuidPart, err := splitPATUUID(accessToken[len(patWirePrefix):])
	if err != nil {
		return ParsedPAT{}, err
	}
	if _, err := uuid.Parse(uuidPart); err != nil {
		return ParsedPAT{}, ErrUnauthenticated
	}
	return ParsedPAT{
		Bearer: accessToken,
		Prefix: patWirePrefix + uuidPart,
	}, nil
}

func splitPATUUID(rest string) (string, error) {
	if len(rest) < 38 { // 36 uuid + _ + min 1 secret char
		return "", ErrUnauthenticated
	}
	if rest[36] != '_' {
		return "", ErrUnauthenticated
	}
	return rest[:36], nil
}
