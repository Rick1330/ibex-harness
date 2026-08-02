package crypto

import "testing"

func TestDummyPHCVerifyCosts(t *testing.T) {
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

func TestDummyPHCRejectsZeroParams(t *testing.T) {
	_, err := DummyPHC(Argon2Params{})
	if err == nil {
		t.Fatal("expected error for zero params")
	}
}
