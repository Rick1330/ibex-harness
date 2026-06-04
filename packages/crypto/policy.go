// Package crypto provides approved cryptographic primitives for IBEX Harness.
// Policy is defined in docs/adr/ADR-0010-cryptography-policy.md.
package crypto

const (
	// SaltLength is the Argon2id salt size in bytes.
	SaltLength = 16
	// KeyLength is the Argon2id derived key size in bytes.
	KeyLength = 32
)

// Argon2Params configures Argon2id hashing and verification.
type Argon2Params struct {
	MemoryKiB   uint32
	Time        uint32
	Parallelism uint8
}

// ProductionParams returns canonical production Argon2id parameters (ADR-0010).
func ProductionParams() Argon2Params {
	return Argon2Params{
		MemoryKiB:   65536,
		Time:        3,
		Parallelism: 4,
	}
}

// TestParams returns a fast Argon2id profile for unit tests only (ADR-0010).
func TestParams() Argon2Params {
	return Argon2Params{
		MemoryKiB:   4096,
		Time:        1,
		Parallelism: 1,
	}
}

// ProductionPHCPrefix is the PHC prefix for hashes created with ProductionParams.
const ProductionPHCPrefix = "$argon2id$v=19$m=65536,t=3,p=4$"
