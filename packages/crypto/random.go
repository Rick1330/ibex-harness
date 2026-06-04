package crypto

import (
	"crypto/rand"
	"math"
)

const base62Alphabet = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"

// GenerateRandomBytes returns n cryptographically secure random bytes.
// Panics if the system entropy source fails (should not happen).
func GenerateRandomBytes(n int) []byte {
	b := make([]byte, n)
	if _, err := rand.Read(b); err != nil {
		panic("crypto/rand unavailable: " + err.Error())
	}
	return b
}

// GenerateRandomBase62 returns a base62 string encoding at least byteLength random bytes.
// Output length is ceil(byteLength * 8 / log2(62)) characters.
func GenerateRandomBase62(byteLength int) string {
	if byteLength <= 0 {
		return ""
	}
	// 62^chars >= 256^byteLength => chars >= byteLength * 8 / log2(62)
	chars := int(math.Ceil(float64(byteLength) * 8 / math.Log2(62)))
	raw := GenerateRandomBytes(chars)
	out := make([]byte, chars)
	for i := 0; i < chars; i++ {
		out[i] = base62Alphabet[int(raw[i])%62]
	}
	return string(out)
}
