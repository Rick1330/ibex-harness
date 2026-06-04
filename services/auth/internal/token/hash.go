package token

import (
	"github.com/Rick1330/ibex-harness/packages/crypto"
)

// HashBearer returns a PHC-encoded Argon2id hash of the full bearer string.
func HashBearer(bearer string, p Argon2Params) (string, error) {
	return crypto.HashToken(bearer, p)
}

// VerifyBearer checks bearer against a PHC Argon2id hash string.
func VerifyBearer(phcHash, bearer string, defaults Argon2Params) (bool, error) {
	return crypto.VerifyToken(bearer, phcHash, defaults)
}
