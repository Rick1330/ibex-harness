package crypto

import (
	"encoding/base64"
	"fmt"
	"strconv"
	"strings"
)

func formatPHC(p Argon2Params, salt, hash []byte) string {
	b64Salt := base64.RawStdEncoding.EncodeToString(salt)
	b64Hash := base64.RawStdEncoding.EncodeToString(hash)
	return fmt.Sprintf("$argon2id$v=19$m=%d,t=%d,p=%d$%s$%s",
		p.MemoryKiB, p.Time, p.Parallelism, b64Salt, b64Hash)
}

func parsePHC(phc string) (mem, time uint32, par uint8, salt, hash []byte, err error) {
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
