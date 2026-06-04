package token

import (
	"strings"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/crypto"
)

func TestHashAndVerifyBearer(t *testing.T) {
	p := DefaultArgon2Params()
	bearer := "ibex_pat_" + "550e8400-e29b-41d4-a716-446655440000" + "_testsecret"
	hash, err := HashBearer(bearer, p)
	if err != nil {
		t.Fatalf("hash: %v", err)
	}
	if !strings.HasPrefix(hash, crypto.ProductionPHCPrefix) {
		t.Fatalf("expected production PHC prefix, got %q", hash[:min(48, len(hash))])
	}
	ok, err := VerifyBearer(hash, bearer, p)
	if err != nil || !ok {
		t.Fatalf("verify: ok=%v err=%v", ok, err)
	}
	ok, err = VerifyBearer(hash, bearer+"x", p)
	if err != nil || ok {
		t.Fatalf("expected verify fail for wrong bearer")
	}
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}
