package token

import (
	"crypto/subtle"
	"encoding/base64"
	"fmt"
	"strconv"
	"strings"

	"golang.org/x/crypto/argon2"
)

// HashBearer returns a PHC-encoded Argon2id hash of the full bearer string.
func HashBearer(bearer string, p Argon2Params) (string, error) {
	salt := make([]byte, 16)
	if _, err := readCryptoRand(salt); err != nil {
		return "", err
	}
	hash := argon2.IDKey([]byte(bearer), salt, p.Time, p.MemoryKiB, p.Parallelism, 32)
	b64Salt := base64.RawStdEncoding.EncodeToString(salt)
	b64Hash := base64.RawStdEncoding.EncodeToString(hash)
	return fmt.Sprintf("$argon2id$v=19$m=%d,t=%d,p=%d$%s$%s",
		p.MemoryKiB, p.Time, p.Parallelism, b64Salt, b64Hash), nil
}

// VerifyBearer checks bearer against a PHC Argon2id hash string.
func VerifyBearer(phcHash, bearer string, defaults Argon2Params) (bool, error) {
	mem, time, par, salt, want, err := parsePHCHash(phcHash)
	if err != nil {
		return false, err
	}
	if mem == 0 {
		mem = defaults.MemoryKiB
	}
	if time == 0 {
		time = defaults.Time
	}
	if par == 0 {
		par = defaults.Parallelism
	}
	got := argon2.IDKey([]byte(bearer), salt, time, mem, par, uint32(len(want)))
	return subtle.ConstantTimeCompare(got, want) == 1, nil
}

func parsePHCHash(phc string) (mem, time uint32, par uint8, salt, hash []byte, err error) {
	parts := strings.Split(phc, "$")
	if len(parts) != 6 || parts[0] != "" || parts[1] != "argon2id" {
		return 0, 0, 0, nil, nil, fmt.Errorf("invalid phc")
	}
	if parts[2] != "v=19" {
		return 0, 0, 0, nil, nil, fmt.Errorf("unsupported version")
	}
	for _, param := range strings.Split(parts[3], ",") {
		kv := strings.SplitN(param, "=", 2)
		if len(kv) != 2 {
			return 0, 0, 0, nil, nil, fmt.Errorf("invalid param")
		}
		switch kv[0] {
		case "m":
			v, e := strconv.ParseUint(kv[1], 10, 32)
			if e != nil {
				return 0, 0, 0, nil, nil, e
			}
			mem = uint32(v)
		case "t":
			v, e := strconv.ParseUint(kv[1], 10, 32)
			if e != nil {
				return 0, 0, 0, nil, nil, e
			}
			time = uint32(v)
		case "p":
			v, e := strconv.ParseUint(kv[1], 10, 8)
			if e != nil {
				return 0, 0, 0, nil, nil, e
			}
			par = uint8(v)
		}
	}
	salt, err = base64.RawStdEncoding.DecodeString(parts[4])
	if err != nil {
		return 0, 0, 0, nil, nil, err
	}
	hash, err = base64.RawStdEncoding.DecodeString(parts[5])
	if err != nil {
		return 0, 0, 0, nil, nil, err
	}
	return mem, time, par, salt, hash, nil
}
