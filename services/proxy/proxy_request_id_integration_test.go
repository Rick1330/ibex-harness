//go:build integration

package proxy_test

import (
	"encoding/json"
	"net/http"
	"strings"
	"testing"
)

func TestProxyRequestID_InErrorEnvelope(t *testing.T) {
	fx := setupProxyAuthFixture(t)

	body := `{"model":"gpt-4","messages":[{"role":"user","content":"hi"}]}`
	resp, respBody := chatPOST(t, chatRequestOpts{
		srvURL: fx.srv.URL, bearer: fx.chatBearer,
		contentType: "application/json", body: body,
	})
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusBadRequest {
		t.Fatalf("status: %d body=%s", resp.StatusCode, respBody)
	}
	if !strings.Contains(respBody, "MISSING_AGENT_ID") {
		t.Fatalf("body: %s", respBody)
	}

	headerID := resp.Header.Get("X-Request-ID")
	if headerID == "" {
		t.Fatal("missing X-Request-ID response header")
	}

	var parsed struct {
		Error struct {
			RequestID string `json:"request_id"`
		} `json:"error"`
	}
	if err := json.Unmarshal([]byte(respBody), &parsed); err != nil {
		t.Fatal(err)
	}
	if parsed.Error.RequestID != headerID {
		t.Fatalf("request_id %q != header %q", parsed.Error.RequestID, headerID)
	}
}
