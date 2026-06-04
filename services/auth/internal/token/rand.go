package token

import "github.com/Rick1330/ibex-harness/packages/crypto"

func readCryptoRand(b []byte) (int, error) {
	copy(b, crypto.GenerateRandomBytes(len(b)))
	return len(b), nil
}
