package token

import (
	"testing"

	"github.com/google/uuid"
)

func TestParsePATValid(t *testing.T) {
	id := uuid.New()
	bearer := "ibex_pat_" + id.String() + "_secretvalue"
	p, err := ParsePAT(bearer)
	if err != nil {
		t.Fatalf("parse: %v", err)
	}
	if p.Bearer != bearer {
		t.Fatalf("bearer mismatch")
	}
	wantPrefix := "ibex_pat_" + id.String()
	if p.Prefix != wantPrefix {
		t.Fatalf("prefix: got %q want %q", p.Prefix, wantPrefix)
	}
}

func TestParsePATRejectsInvalid(t *testing.T) {
	cases := []string{
		"",
		"ibex_jwt_x",
		"ibex_pat_not-a-uuid_x",
		"ibex_pat_" + uuid.New().String(),
		"ibex_pat_" + uuid.New().String() + "_",
	}
	for _, c := range cases {
		if _, err := ParsePAT(c); err == nil {
			t.Fatalf("expected error for %q", c)
		}
	}
}
