package crypto

import (
	"golang.org/x/crypto/argon2"
)

// HashSecret returns a PHC-encoded Argon2id hash of plaintext using params.
func HashSecret(plaintext string, p Argon2Params) (string, error) {
	salt := GenerateRandomBytes(SaltLength)
	digest := argon2.IDKey([]byte(plaintext), salt, p.Time, p.MemoryKiB, p.Parallelism, KeyLength)
	return formatPHC(p, salt, digest), nil
}

// VerifySecret checks plaintext against a PHC Argon2id hash.
// Wrong password returns (false, nil). Malformed PHC returns (false, err).
func VerifySecret(plaintext, phcHash string, fallback Argon2Params) (bool, error) {
	mem, time, par, salt, want, err := parsePHC(phcHash)
	if err != nil {
		return false, err
	}
	if mem == 0 {
		mem = fallback.MemoryKiB
	}
	if time == 0 {
		time = fallback.Time
	}
	if par == 0 {
		par = fallback.Parallelism
	}
	got := argon2.IDKey([]byte(plaintext), salt, time, mem, par, uint32(len(want)))
	return ConstantTimeEqualBytes(got, want), nil
}

// HashPassword hashes a password with production-equivalent params (caller supplies params).
func HashPassword(password string, p Argon2Params) (string, error) {
	return HashSecret(password, p)
}

// VerifyPassword verifies a password against a PHC hash.
func VerifyPassword(password, phcHash string, fallback Argon2Params) (bool, error) {
	return VerifySecret(password, phcHash, fallback)
}

// HashToken hashes a token bearer string (same Argon2id policy as passwords).
func HashToken(plaintext string, p Argon2Params) (string, error) {
	return HashSecret(plaintext, p)
}

// VerifyToken verifies a token bearer against a PHC hash.
func VerifyToken(plaintext, phcHash string, fallback Argon2Params) (bool, error) {
	return VerifySecret(plaintext, phcHash, fallback)
}
