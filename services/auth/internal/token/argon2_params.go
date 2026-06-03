package token

// Argon2Params configures Argon2id verify (must match stored PHC hashes).
type Argon2Params struct {
	MemoryKiB   uint32
	Time        uint32
	Parallelism uint8
}

// DefaultArgon2Params matches ENVIRONMENT_VARIABLES.md defaults.
func DefaultArgon2Params() Argon2Params {
	return Argon2Params{
		MemoryKiB:   65536,
		Time:        3,
		Parallelism: 2,
	}
}
