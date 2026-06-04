package crypto

import "testing"

func TestRandomEntropy(t *testing.T) {
	seen := make(map[string]bool, 10000)
	for i := 0; i < 10000; i++ {
		token := GenerateRandomBase62(32)
		if seen[token] {
			t.Fatalf("collision detected at iteration %d", i)
		}
		seen[token] = true
	}
}

func TestGenerateRandomBytesLength(t *testing.T) {
	b := GenerateRandomBytes(16)
	if len(b) != 16 {
		t.Fatalf("len=%d", len(b))
	}
}

func TestConstantTimeEqual(t *testing.T) {
	if !ConstantTimeEqual("abc", "abc") {
		t.Fatal("expected equal")
	}
	if ConstantTimeEqual("abc", "abd") {
		t.Fatal("expected not equal")
	}
}
