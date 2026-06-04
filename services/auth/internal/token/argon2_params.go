package token

import "github.com/Rick1330/ibex-harness/packages/crypto"

// Argon2Params configures Argon2id verify (must match stored PHC hashes).
type Argon2Params = crypto.Argon2Params

// DefaultArgon2Params returns ADR-0010 production parameters.
func DefaultArgon2Params() Argon2Params {
	return crypto.ProductionParams()
}
