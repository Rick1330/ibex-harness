package crypto

import (
	"fmt"

	"golang.org/x/crypto/argon2"
)

// DummyPHC returns a PHC-encoded Argon2id hash suitable for miss-path timing
// equalization. Callers should create one DummyPHC per process (or Validator)
// and reuse it so salt/digest work is paid only at startup, while each miss
// still runs a full IDKey via VerifySecret against this fixed PHC.
func DummyPHC(p Argon2Params) (string, error) {
	if err := validateArgon2Params(p); err != nil {
		return "", err
	}
	salt := GenerateRandomBytes(SaltLength)
	// Fixed sentinel plaintext — never used as a real credential.
	digest := argon2.IDKey([]byte("ibex-dummy-verify-sentinel"), salt, p.Time, p.MemoryKiB, p.Parallelism, KeyLength)
	return formatPHC(p, salt, digest), nil
}

func validateArgon2Params(p Argon2Params) error {
	if p.MemoryKiB == 0 || p.Time == 0 || p.Parallelism == 0 {
		return fmt.Errorf("crypto: Argon2Params must be non-zero")
	}
	return nil
}
