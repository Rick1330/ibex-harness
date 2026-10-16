package responses

import (
	"bytes"
	"encoding/json"
	"testing"
)

func TestParseResponsePreservesOrderAndUnknownRaw(t *testing.T) {
	body := []byte(`{"id":"resp_1","object":"response","status":"completed","output":[{"type":"reasoning","id":"r1","encrypted_content":"opaque"},{"type":"future_item","x":{"keep":true}},{"type":"message","id":"m1","role":"assistant","content":[{"type":"output_text","text":"ok"}]}]}`)
	got, err := ParseResponse(body)
	if err != nil {
		t.Fatal(err)
	}
	wantTypes := []string{"reasoning", "future_item", "message"}
	if len(got.Output) != len(wantTypes) {
		t.Fatalf("output len=%d want=%d", len(got.Output), len(wantTypes))
	}
	for i, want := range wantTypes {
		if got.Output[i].Type != want {
			t.Fatalf("output[%d].Type=%q want %q", i, got.Output[i].Type, want)
		}
	}
	if got.Output[1].Message != nil {
		t.Fatalf("unknown item decoded as known type: %+v", got.Output[1])
	}
	if string(got.Output[1].Raw) != `{"type":"future_item","x":{"keep":true}}` {
		t.Fatalf("unknown item lost raw=%s", got.Output[1].Raw)
	}
	if got.Output[0].Reasoning == nil || got.Output[0].Reasoning.EncryptedContent != "opaque" {
		t.Fatal("reasoning not decoded")
	}
}

func TestRequestValidation(t *testing.T) {
	if _, err := MarshalRequest(Request{}); err == nil {
		t.Fatal("missing model must fail")
	}
	if _, err := MarshalRequest(Request{Model: "gpt-4o", MaxOutputTokens: -1}); err == nil {
		t.Fatal("negative max output must fail")
	}
}

func TestRequestPreservesRawInputAndRequiredCapabilities(t *testing.T) {
	r := Request{Model: "gpt-4o", Input: []byte(`{"value":9007199254740993}`), Reasoning: &Reasoning{Effort: "low"}, Tools: []json.RawMessage{json.RawMessage(`{"type":"function"}`)}, PreviousResponseID: "resp_1"}
	b, err := MarshalRequest(r)
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Contains(b, []byte("9007199254740993")) {
		t.Fatalf("numeric input was not preserved: %s", b)
	}
	want := []string{"responses", "reasoning", "tools", "previous_response_id"}
	got := r.RequiredCapabilities()
	if len(got) != len(want) {
		t.Fatalf("caps=%v", got)
	}
	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("caps=%v want=%v", got, want)
		}
	}
}

func TestParseResponseRejectsMalformedOutputDiscriminator(t *testing.T) {
	if _, err := ParseResponse([]byte(`{"output":[{"id":"missing-type"}]}`)); err == nil {
		t.Fatal("missing discriminator must fail")
	}
}

func TestParseResponseFunctionItemsAndUsageValidation(t *testing.T) {
	body := []byte(`{"usage":{"input_tokens":2,"output_tokens":3,"total_tokens":5},"output":[{"type":"function_call","id":"fc","call_id":"c","name":"lookup","arguments":"{}"},{"type":"function_call_output","call_id":"c","output":"ok"}]}`)
	got, err := ParseResponse(body)
	if err != nil {
		t.Fatal(err)
	}
	if got.Output[0].FunctionCall == nil || got.Output[1].FunctionCallOutput == nil {
		t.Fatalf("items=%+v", got.Output)
	}
	if _, err := ParseResponse([]byte(`{"usage":{"input_tokens":2,"output_tokens":3,"total_tokens":6}}`)); err == nil {
		t.Fatal("inconsistent usage must fail")
	}
}

func TestDecodeOrderedItems(t *testing.T) {
	items, err := DecodeOrderedItems(bytes.NewReader([]byte(`{"output":[{"type":"message","role":"assistant"},{"type":"future","x":1}]}`)))
	if err != nil || len(items) != 2 || items[1].Type != "future" {
		t.Fatalf("items=%+v err=%v", items, err)
	}
	if _, err := DecodeOrderedItems(bytes.NewReader([]byte(`{"output":{}}`))); err == nil {
		t.Fatal("non-array must fail")
	}
}
