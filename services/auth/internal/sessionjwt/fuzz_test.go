package sessionjwt

import "testing"

func FuzzSplitJWTAndHeader(f *testing.F) {
	f.Add("eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.a.b")
	f.Add("")
	f.Add("a.b.c.d")
	f.Fuzz(func(t *testing.T, raw string) {
		parts, err := splitJWT(raw)
		if err != nil {
			return
		}
		_ = validateHeader(parts.header)
	})
}
