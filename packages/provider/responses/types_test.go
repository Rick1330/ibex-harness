package responses

import "testing"

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
