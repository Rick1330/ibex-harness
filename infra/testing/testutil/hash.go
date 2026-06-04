//go:build integration

package testutil

import (
	"crypto/rand"
	"encoding/base64"
	"fmt"

	"golang.org/x/crypto/argon2"
)

// argon2Params matches services/auth/internal/token DefaultArgon2Params (ADR-0007 defaults).
var argon2Params = struct {
	MemoryKiB   uint32
	Time        uint32
	Parallelism uint8
}{65536, 3, 2}

func hashBearerForTest(bearer string) (string, error) {
	salt := make([]byte, 16)
	if _, err := rand.Read(salt); err != nil {
		return "", err
	}
	hash := argon2.IDKey([]byte(bearer), salt, argon2Params.Time, argon2Params.MemoryKiB, argon2Params.Parallelism, 32)
	b64Salt := base64.RawStdEncoding.EncodeToString(salt)
	b64Hash := base64.RawStdEncoding.EncodeToString(hash)
	return fmt.Sprintf("$argon2id$v=19$m=%d,t=%d,p=%d$%s$%s",
		argon2Params.MemoryKiB, argon2Params.Time, argon2Params.Parallelism, b64Salt, b64Hash), nil
}
