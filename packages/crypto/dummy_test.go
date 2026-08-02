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
	cases := []struct {
		name string
		p    Argon2Params
	}{
		{name: "all_zero", p: Argon2Params{}},
		{name: "zero_memory", p: Argon2Params{MemoryKiB: 0, Time: 1, Parallelism: 1}},
		{name: "zero_time", p: Argon2Params{MemoryKiB: 1, Time: 0, Parallelism: 1}},
		{name: "zero_parallelism", p: Argon2Params{MemoryKiB: 1, Time: 1, Parallelism: 0}},
	}
	for _, tc := range cases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			_, err := DummyPHC(tc.p)
			if !errors.Is(err, ErrInvalidArgon2Params) {
				t.Fatalf("want ErrInvalidArgon2Params, got %v", err)
			}
		})
	}
}
