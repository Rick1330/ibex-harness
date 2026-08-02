package token

import "github.com/Rick1330/ibex-harness/packages/crypto"

// Argon2Params is the auth-service alias for crypto.Argon2Params.
type Argon2Params = crypto.Argon2Params

// DefaultArgon2Params returns ADR-0010 production parameters.
func DefaultArgon2Params() Argon2Params {
	return crypto.ProductionParams()
}

// TestArgon2Params returns the fast Argon2id profile for unit tests only.
func TestArgon2Params() Argon2Params {
	return crypto.TestParams()
}
