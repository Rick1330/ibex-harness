package crypto

import "crypto/subtle"

// ConstantTimeEqual compares two strings in constant time.
func ConstantTimeEqual(a, b string) bool {
	return subtle.ConstantTimeCompare([]byte(a), []byte(b)) == 1
}

// ConstantTimeEqualBytes compares two byte slices in constant time.
func ConstantTimeEqualBytes(a, b []byte) bool {
	return subtle.ConstantTimeCompare(a, b) == 1
}
