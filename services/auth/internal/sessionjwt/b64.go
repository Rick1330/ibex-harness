package sessionjwt

import "encoding/base64"

func rawURLEncode(b []byte) string {
	return base64.RawURLEncoding.EncodeToString(b)
}

func rawURLDecode(s string) ([]byte, error) {
	return base64.RawURLEncoding.DecodeString(s)
}
