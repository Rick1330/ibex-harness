package canonicaljson

import (
	"bytes"
	"encoding/json"
	"os"
	"testing"
)

type contractVectors struct {
	Vectors []struct {
		Name          string          `json:"name"`
		Input         json.RawMessage `json:"input"`
		CanonicalUTF8 string          `json:"canonical_utf8"`
		SHA256        string          `json:"sha256"`
	} `json:"vectors"`
}

func TestContractVectors(t *testing.T) {
	raw, err := os.ReadFile("../../web/engineering/architecture-v2/contracts/jcs-test-vectors.json")
	if err != nil {
		t.Fatal(err)
	}
	var vectors contractVectors
	if err := json.Unmarshal(raw, &vectors); err != nil {
		t.Fatal(err)
	}
	if len(vectors.Vectors) == 0 {
		t.Fatal("contract vectors are empty")
	}
	for _, vector := range vectors.Vectors {
		vector := vector
		t.Run(vector.Name, func(t *testing.T) {
			canonical, digest, err := Digest(vector.Input)
			if err != nil {
				t.Fatal(err)
			}
			if !bytes.Equal(canonical, []byte(vector.CanonicalUTF8)) {
				t.Fatalf("canonical=%q want %q", canonical, vector.CanonicalUTF8)
			}
			if digest != vector.SHA256 {
				t.Fatalf("digest=%q want %q", digest, vector.SHA256)
			}
		})
	}
}

func TestCanonicalizeRejectsMalformedJSON(t *testing.T) {
	for _, input := range []string{"{", "[1,", "{\"a\":}", `{"a":+1}`} {
		if _, err := Canonicalize([]byte(input)); err == nil {
			t.Fatalf("input %q was accepted", input)
		}
		if _, _, err := Digest([]byte(input)); err == nil {
			t.Fatalf("Digest accepted malformed input %q", input)
		}
	}
}

func TestCanonicalizeRejectsDuplicateObjectNames(t *testing.T) {
	if _, err := Canonicalize([]byte(`{"a":1,"a":2}`)); err == nil {
		t.Fatal("duplicate object names were accepted")
	}
}

func TestCanonicalizeObjectAndArrayRoots(t *testing.T) {
	tests := []struct {
		name  string
		input string
		want  string
	}{
		{name: "object", input: `{"b":2,"a":1}`, want: `{"a":1,"b":2}`},
		{name: "array", input: `[2,1]`, want: `[2,1]`},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			got, err := Canonicalize([]byte(tc.input))
			if err != nil {
				t.Fatal(err)
			}
			if string(got) != tc.want {
				t.Fatalf("canonical=%q want %q", got, tc.want)
			}
		})
	}
}

func TestCanonicalizeScalarRoots(t *testing.T) {
	tests := []struct {
		name  string
		input string
		want  string
	}{
		{name: "true", input: `true`, want: `true`},
		{name: "false", input: `false`, want: `false`},
		{name: "null", input: `null`, want: `null`},
		{name: "number", input: `1.0`, want: `1`},
		{name: "string", input: `"a\/b"`, want: `"a/b"`},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			got, err := Canonicalize([]byte(tc.input))
			if err != nil {
				t.Fatal(err)
			}
			if string(got) != tc.want {
				t.Fatalf("canonical=%q want %q", got, tc.want)
			}
		})
	}
}
