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
	if len(got.Output) != 3 || got.Output[0].Type != "reasoning" || got.Output[1].Type != "future_item" || got.Output[2].Type != "message" {
		t.Fatalf("order/types=%+v", got.Output)
	}
	if got.Output[1].Message != nil || string(got.Output[1].Raw) != `{"type":"future_item","x":{"keep":true}}` {
		t.Fatalf("unknown item lost raw=%s", got.Output[1].Raw)
	}
	if got.Output[0].Reasoning == nil || got.Output[0].Reasoning.EncryptedContent != "opaque" {
		t.Fatalf("reasoning not decoded")
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
