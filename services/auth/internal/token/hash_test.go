package token

import "testing"

func TestHashAndVerifyBearer(t *testing.T) {
	p := DefaultArgon2Params()
	bearer := "ibex_pat_" + "550e8400-e29b-41d4-a716-446655440000" + "_testsecret"
	hash, err := HashBearer(bearer, p)
	if err != nil {
		t.Fatalf("hash: %v", err)
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
