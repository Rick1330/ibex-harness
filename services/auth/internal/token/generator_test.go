package token

import (
	"strings"
	"testing"
)

func TestGeneratePATFormat(t *testing.T) {
	plaintext, prefix, rowID, err := GeneratePAT()
	if err != nil {
		t.Fatal(err)
	}
	if !strings.HasPrefix(plaintext, patWirePrefix) {
		t.Fatalf("plaintext prefix: %s", plaintext)
	}
	if prefix != patWirePrefix+rowID.String() {
		t.Fatalf("prefix mismatch: %s vs %s", prefix, rowID)
	}
	parsed, err := ParsePAT(plaintext)
	if err != nil {
		t.Fatal(err)
	}
	if parsed.Prefix != prefix {
		t.Fatalf("parsed prefix %s want %s", parsed.Prefix, prefix)
	}
	secret := plaintext[len(prefix)+1:]
	if len(secret) < 32 {
		t.Fatalf("secret too short: %d", len(secret))
	}
}

func TestGeneratePATUnique(t *testing.T) {
	a, _, _, _ := GeneratePAT()
	b, _, _, _ := GeneratePAT()
	if a == b {
		t.Fatal("expected unique tokens")
	}
}
