package token

import (
	"strings"
	"testing"

	"github.com/google/uuid"
)

func TestUnit_ParsePATValid(t *testing.T) {
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

func TestUnit_ParsePATRejectsInvalid(t *testing.T) {
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

func TestUnit_ParsePATRejectsOversized(t *testing.T) {
	t.Parallel()
	id := uuid.New()
	secret := strings.Repeat("a", maxPATLen)
	bearer := "ibex_pat_" + id.String() + "_" + secret
	if len(bearer) <= maxPATLen {
		t.Fatalf("test fixture must exceed maxPATLen=%d; got %d", maxPATLen, len(bearer))
	}
	if _, err := ParsePAT(bearer); err == nil {
		t.Fatal("expected ErrUnauthenticated for oversized PAT")
	}
}

func TestUnit_ParsePATRejectsWhitespacePaddingBypass(t *testing.T) {
	t.Parallel()
	id := uuid.New()
	valid := "ibex_pat_" + id.String() + "_secretvalue"
	padded := strings.Repeat(" ", maxPATLen) + valid
	if len(padded) <= maxPATLen {
		t.Fatalf("fixture must exceed maxPATLen before trim; got %d", len(padded))
	}
	if _, err := ParsePAT(padded); err == nil {
		t.Fatal("whitespace padding must not bypass maxPATLen")
	}
}

func TestUnit_ParsePATAcceptsGeneratedShape(t *testing.T) {
	t.Parallel()
	plaintext, _, _, err := GeneratePAT()
	if err != nil {
		t.Fatal(err)
	}
	if len(plaintext) > maxPATLen {
		t.Fatalf("generated PAT len=%d exceeds maxPATLen=%d", len(plaintext), maxPATLen)
	}
	if _, err := ParsePAT(plaintext); err != nil {
		t.Fatalf("ParsePAT generated: %v", err)
	}
}
