package token

import (
	"encoding/base64"
	"fmt"

	"github.com/google/uuid"
)

// GeneratePAT builds a new PAT wire value per ADR-0007: ibex_pat_<uuid>_<secret>.
// rowID is used as the token row UUID and embedded in prefix/wire form.
func GeneratePAT() (plaintext, prefix string, rowID uuid.UUID, err error) {
	rowID = uuid.New()
	secret := make([]byte, 32)
	if _, err = readCryptoRand(secret); err != nil {
		return "", "", uuid.Nil, fmt.Errorf("rand secret: %w", err)
	}
	encoded := base64.RawURLEncoding.EncodeToString(secret)
	prefix = patWirePrefix + rowID.String()
	plaintext = prefix + "_" + encoded
	if _, err = ParsePAT(plaintext); err != nil {
		return "", "", uuid.Nil, fmt.Errorf("generated PAT invalid: %w", err)
	}
	return plaintext, prefix, rowID, nil
}
