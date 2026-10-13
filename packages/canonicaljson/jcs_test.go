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
	for _, input := range []string{"{", "[1,", "{\"a\":}"} {
		if _, err := Canonicalize([]byte(input)); err == nil {
			t.Fatalf("input %q was accepted", input)
		}
	}
}

func TestCanonicalizeRejectsDuplicateObjectNames(t *testing.T) {
	if _, err := Canonicalize([]byte(`{"a":1,"a":2}`)); err == nil {
		t.Fatal("duplicate object names were accepted")
	}
}
