package session

import (
	"errors"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/google/uuid"
)

func TestUnit_ReadLimitedBody(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name    string
		input   string
		limit   int64
		want    string
		wantErr error
	}{
		{name: "exact limit", input: "abc", limit: 3, want: "abc"},
		{name: "over limit", input: "abcd", limit: 3, wantErr: ErrProviderResponseTooLarge},
		{name: "empty", input: "", limit: 10, want: ""},
	}
	for _, tc := range tests {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			got, err := readLimitedBody(strings.NewReader(tc.input), tc.limit)
			if tc.wantErr != nil {
				if !errors.Is(err, tc.wantErr) {
					t.Fatalf("err=%v want %v", err, tc.wantErr)
				}
				return
			}
			if err != nil {
				t.Fatalf("unexpected err=%v", err)
			}
			if string(got) != tc.want {
				t.Fatalf("got=%q want=%q", got, tc.want)
			}
		})
	}
}

func TestUnit_ReadAllBody(t *testing.T) {
	t.Parallel()
	got, err := ReadAllBody(strings.NewReader("payload"))
	if err != nil {
		t.Fatal(err)
	}
	if string(got) != "payload" {
		t.Fatalf("got=%q", got)
	}
}

func TestUnit_StickyExternalID(t *testing.T) {
	t.Parallel()

	validID := uuid.New().String()
	tooLong := strings.Repeat("x", maxExternalIDLen+1)

	tests := []struct {
		name      string
		raw       string
		wantExact string
		wantMint  bool
	}{
		{name: "empty mints uuid", raw: "", wantMint: true},
		{name: "whitespace mints uuid", raw: "   ", wantMint: true},
		{name: "trim preserves", raw: "  abc  ", wantExact: "abc"},
		{name: "at max length", raw: strings.Repeat("a", maxExternalIDLen), wantExact: strings.Repeat("a", maxExternalIDLen)},
		{name: "over max mints uuid", raw: tooLong, wantMint: true},
		{name: "valid uuid passthrough", raw: validID, wantExact: validID},
	}
	for _, tc := range tests {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			got := StickyExternalID(tc.raw)
			if tc.wantExact != "" && got != tc.wantExact {
				t.Fatalf("got=%q want=%q", got, tc.wantExact)
			}
			if tc.wantMint {
				assertValidUUID(t, got)
			}
		})
	}
}

func TestUnit_CompletionTextFromJSON(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name string
		body string
		want string
	}{
		{name: "extracts content", body: `{"choices":[{"message":{"content":"hi"}}]}`, want: "hi"},
		{name: "bad json", body: `{`, want: ""},
		{name: "empty choices", body: `{"choices":[]}`, want: ""},
		{name: "missing choices", body: `{}`, want: ""},
		{name: "empty content", body: `{"choices":[{"message":{"content":""}}]}`, want: ""},
	}
	for _, tc := range tests {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			got := CompletionTextFromJSON([]byte(tc.body))
			if got != tc.want {
				t.Fatalf("got=%q want=%q", got, tc.want)
			}
		})
	}
}

func TestUnit_WriteJSONBody(t *testing.T) {
	t.Parallel()
	rec := httptest.NewRecorder()
	body := []byte(`{"ok":true}`)
	WriteJSONBody(rec, body)
	if rec.Body.String() != string(body) {
		t.Fatalf("body=%q", rec.Body.String())
	}
}

func TestUnit_SetResponseHeader(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name       string
		externalID string
		wantHeader string
	}{
		{name: "sets header", externalID: "sess-1", wantHeader: "sess-1"},
		{name: "skips empty", externalID: "", wantHeader: ""},
	}
	for _, tc := range tests {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			rec := httptest.NewRecorder()
			SetResponseHeader(rec, Resolved{ExternalID: tc.externalID})
			got := rec.Header().Get(HeaderSessionID)
			if got != tc.wantHeader {
				t.Fatalf("header=%q want=%q", got, tc.wantHeader)
			}
		})
	}
}

func assertValidUUID(t *testing.T, s string) {
	t.Helper()
	if _, err := uuid.Parse(s); err != nil {
		t.Fatalf("uuid.Parse(%q): %v", s, err)
	}
}
