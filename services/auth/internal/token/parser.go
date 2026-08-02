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
	accessToken = strings.TrimSpace(accessToken)
	if accessToken == "" || len(accessToken) > maxPATLen {
		return ParsedPAT{}, ErrUnauthenticated
	}
	if !strings.HasPrefix(accessToken, patWirePrefix) {
		return ParsedPAT{}, ErrUnauthenticated
	}
	rest := accessToken[len(patWirePrefix):]
	if len(rest) < 38 { // 36 uuid + _ + min 1 secret char
		return ParsedPAT{}, ErrUnauthenticated
	}
	uuidPart := rest[:36]
	if rest[36] != '_' {
		return ParsedPAT{}, ErrUnauthenticated
	}
	secret := rest[37:]
	if secret == "" {
		return ParsedPAT{}, ErrUnauthenticated
	}
	if _, err := uuid.Parse(uuidPart); err != nil {
		return ParsedPAT{}, ErrUnauthenticated
	}
	return ParsedPAT{
		Bearer: accessToken,
		Prefix: patWirePrefix + uuidPart,
	}, nil
}
