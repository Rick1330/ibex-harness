package crypto

import (
	"errors"
	"testing"
)

func TestUnit_DummyPHC_VerifyCosts(t *testing.T) {
	p := TestParams()
	dummy, err := DummyPHC(p)
	if err != nil {
		t.Fatalf("DummyPHC: %v", err)
	}
	ok, err := VerifySecret("attacker-guess", dummy, p)
	if err != nil {
		t.Fatalf("verify dummy: %v", err)
	}
	if ok {
		t.Fatal("dummy verify must never succeed for arbitrary plaintext")
	}
}

func TestUnit_DummyPHC_RejectsZeroParams(t *testing.T) {
	_, err := DummyPHC(Argon2Params{})
	if !errors.Is(err, ErrInvalidArgon2Params) {
		t.Fatalf("want ErrInvalidArgon2Params, got %v", err)
	}
}
