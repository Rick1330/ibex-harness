package responses

import (
	"bytes"
	"encoding/json"
	"errors"
	"testing"
)

func TestRequestValidationRequiresReasoningEffort(t *testing.T) {
	if err := (Request{Model: "gpt-4o", Reasoning: &Reasoning{}}).Validate(); !errors.Is(err, ErrInvalid) {
		t.Fatalf("empty reasoning effort must fail: %v", err)
	}
}

func TestParseResponseDecodeFailures(t *testing.T) {
	cases := map[string]string{
		"message role type":            `{"output":[{"type":"message","role":5}]}`,
		"reasoning summary type":       `{"output":[{"type":"reasoning","summary":5}]}`,
		"function call call_id type":   `{"output":[{"type":"function_call","call_id":5}]}`,
		"function output call_id type": `{"output":[{"type":"function_call_output","call_id":5}]}`,
	}
	for name, body := range cases {
		t.Run(name, func(t *testing.T) {
			if _, err := ParseResponse([]byte(body)); !errors.Is(err, ErrInvalid) {
				t.Fatalf("err=%v", err)
			}
		})
	}
	if _, err := ParseResponse([]byte(`not-json`)); !errors.Is(err, ErrInvalid) {
		t.Fatalf("malformed body err=%v", err)
	}
}

func TestParseItemRejectsInvalidRawAndEmptyDiscriminator(t *testing.T) {
	if _, err := parseItem(json.RawMessage(`{bad`)); !errors.Is(err, ErrInvalid) {
		t.Fatalf("invalid raw err=%v", err)
	}
	if _, err := parseItem(json.RawMessage(`{"id":"x"}`)); !errors.Is(err, ErrInvalid) {
		t.Fatalf("empty discriminator err=%v", err)
	}
}

func TestDecodeOrderedItemsReadAndDecodeFailures(t *testing.T) {
	if _, err := DecodeOrderedItems(errReader{}); err == nil {
		t.Fatal("read error must surface")
	}
	if _, err := DecodeOrderedItems(bytes.NewReader([]byte(`{"output":[{"id":"no-type"}]}`))); !errors.Is(err, ErrInvalid) {
		t.Fatalf("invalid item err=%v", err)
	}
}

type errReader struct{}

func (errReader) Read([]byte) (int, error) { return 0, errors.New("boom") }
