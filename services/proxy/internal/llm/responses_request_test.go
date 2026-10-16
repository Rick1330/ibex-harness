package llm

import (
	"context"
	"strings"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/provider/responses"
)

func TestResponsesRequestContextRoundTrip(t *testing.T) {
	req := responses.Request{Model: "gpt-4o"}
	got, ok := ResponsesRequestFromContext(WithResponsesRequest(context.Background(), req))
	if !ok || got.Model != req.Model {
		t.Fatalf("got=%+v ok=%v", got, ok)
	}
	if _, ok := ResponsesRequestFromContext(context.Background()); ok {
		t.Fatal("unexpected request")
	}
}

func TestParseResponsesRequestValidatesAndRejectsTrailingData(t *testing.T) {
	got, err := ParseResponsesRequest(strings.NewReader(`{"model":"  gpt-4o  "}`))
	if err != nil || got.Model != "gpt-4o" {
		t.Fatalf("got=%+v err=%v", got, err)
	}
	for _, body := range []string{`{"model":"   "}`, `{"model":"gpt-4o"}{"model":"gpt-4o"}`, `{bad}`} {
		if _, err := ParseResponsesRequest(strings.NewReader(body)); err == nil {
			t.Fatalf("body should fail: %s", body)
		}
	}
}
