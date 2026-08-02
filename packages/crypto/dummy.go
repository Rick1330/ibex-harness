package crypto

import (
	"errors"
	"fmt"

	"golang.org/x/crypto/argon2"
)

// ErrInvalidArgon2Params lets callers detect zero/invalid Argon2Params via errors.Is.
var ErrInvalidArgon2Params = errors.New("crypto: Argon2Params must be non-zero")

// DummyPHC returns a PHC-encoded Argon2id hash suitable for miss-path timing
// equalization. Callers should create one DummyPHC per process (or Validator)
// and reuse it so salt/digest work is paid only at startup, while each miss
// still runs a full IDKey via VerifySecret against this PHC.
//
// The hashed plaintext is random process entropy — not a credential.
func DummyPHC(p Argon2Params) (string, error) {
	if err := validateArgon2Params(p); err != nil {
		return "", err
	}
	salt := GenerateRandomBytes(SaltLength)
	plaintext := GenerateRandomBytes(KeyLength)
	digest := argon2.IDKey(plaintext, salt, p.Time, p.MemoryKiB, p.Parallelism, KeyLength)
	return formatPHC(p, salt, digest), nil
}

func validateArgon2Params(p Argon2Params) error {
	if p.MemoryKiB == 0 {
		return fmt.Errorf("%w: MemoryKiB", ErrInvalidArgon2Params)
	}
	if p.Time == 0 {
		return fmt.Errorf("%w: Time", ErrInvalidArgon2Params)
	}
	if p.Parallelism == 0 {
		return fmt.Errorf("%w: Parallelism", ErrInvalidArgon2Params)
	}
	return nil
}
