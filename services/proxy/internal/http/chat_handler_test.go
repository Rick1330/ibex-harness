package http

import (
	"strings"
	"testing"
)

func TestChatCompletions(t *testing.T) {
	t.Parallel()
	for _, tc := range chatCompletionCases() {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			runChatCompletionCase(t, tc)
		})
	}
}

func runChatCompletionCase(t *testing.T, tc chatCompletionCase) {
	t.Helper()
	rec := postChat(t, chatTestHandler(t, tc.validator, tc.cfg), tc.req)
	if rec.Code != tc.wantStatus {
		t.Fatalf("status: %d body=%s", rec.Code, rec.Body.String())
	}
	if tc.wantBody != "" && !strings.Contains(rec.Body.String(), tc.wantBody) {
		t.Fatalf("body: %s", rec.Body.String())
	}
}
