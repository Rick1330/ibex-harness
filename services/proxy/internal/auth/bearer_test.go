package auth

import (
	"testing"
)

func TestParseAuthorizationHeader(t *testing.T) {
	token, err := ParseAuthorizationHeader("Bearer ibex_pat_abc")
	if err != nil || token != "ibex_pat_abc" {
		t.Fatalf("got %q err=%v", token, err)
	}
	_, err = ParseAuthorizationHeader("")
	if err != ErrMissingToken {
		t.Fatalf("expected missing token, got %v", err)
	}
	_, err = ParseAuthorizationHeader("Bearer ")
	if err != ErrMissingToken {
		t.Fatalf("expected missing token for empty bearer, got %v", err)
	}
	_, err = ParseAuthorizationHeader("Basic abc")
	if err == nil {
		t.Fatal("expected error for non-bearer scheme")
	}
}
