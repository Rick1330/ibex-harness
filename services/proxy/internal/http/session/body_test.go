package session

import (
	"errors"
	"strings"
	"testing"
)

func TestUnit_ReadLimitedBody(t *testing.T) {
	t.Parallel()

	ok, err := readLimitedBody(strings.NewReader("abc"), 3)
	if err != nil || string(ok) != "abc" {
		t.Fatalf("ok=%q err=%v", ok, err)
	}

	_, err = readLimitedBody(strings.NewReader("abcd"), 3)
	if !errors.Is(err, ErrProviderResponseTooLarge) {
		t.Fatalf("err=%v", err)
	}
}

func TestUnit_StickyExternalID(t *testing.T) {
	t.Parallel()
	minted := StickyExternalID("")
	if minted == "" {
		t.Fatal("expected mint")
	}
	got := StickyExternalID("  abc  ")
	if got != "abc" {
		t.Fatalf("got=%q", got)
	}
	tooLong := strings.Repeat("x", maxExternalIDLen+1)
	replaced := StickyExternalID(tooLong)
	if replaced == tooLong || replaced == "" {
		t.Fatal("expected mint replacing oversized")
	}
}

func TestUnit_CompletionTextFromJSON(t *testing.T) {
	t.Parallel()
	got := CompletionTextFromJSON([]byte(`{"choices":[{"message":{"content":"hi"}}]}`))
	if got != "hi" {
		t.Fatalf("got=%q", got)
	}
	if CompletionTextFromJSON([]byte(`{`)) != "" {
		t.Fatal("expected empty on bad json")
	}
}
