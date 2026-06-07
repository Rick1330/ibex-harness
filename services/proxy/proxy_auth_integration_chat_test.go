//go:build integration

package proxy_test

import (
	"net/http"
	"strings"
	"testing"

	"github.com/Rick1330/ibex-harness/services/proxy/internal/validation"
)

type chatCase struct {
	name          string
	bearer        string
	agentID       string
	contentType   string
	body          string
	wantStatus    int
	wantBodyParts []string
	checkHeaders  bool
}

func buildChatCases(fx proxyAuthFixture) []chatCase {
	return []chatCase{
		{
			name: "chat without permission", bearer: fx.lowPermsBearer, agentID: fx.agentA,
			contentType: "application/json", body: "{}", wantStatus: http.StatusForbidden,
		},
		{
			name: "chat stub with permission", bearer: fx.chatBearer, agentID: fx.agentA,
			contentType: "application/json",
			body:        `{"model":"gpt-4","messages":[{"role":"user","content":"hi"}]}`,
			wantStatus:  http.StatusNotImplemented, wantBodyParts: []string{"PROVIDER_NOT_CONFIGURED"}, checkHeaders: true,
		},
		{
			name: "chat malformed json", bearer: fx.chatBearer, agentID: fx.agentA,
			contentType: "application/json", body: `{invalid`,
			wantStatus: http.StatusBadRequest, wantBodyParts: []string{"INVALID_JSON"},
		},
		{
			name: "chat missing model", bearer: fx.chatBearer, agentID: fx.agentA,
			contentType: "application/json", body: `{"messages":[{"role":"user","content":"hi"}]}`,
			wantStatus: http.StatusBadRequest, wantBodyParts: []string{"VALIDATION_ERROR", `"field":"model"`}, checkHeaders: true,
		},
		{
			name: "chat missing agent header", bearer: fx.chatBearer,
			contentType: "application/json",
			body:        `{"model":"gpt-4","messages":[{"role":"user","content":"hi"}]}`,
			wantStatus:  http.StatusBadRequest, wantBodyParts: []string{"MISSING_AGENT_ID"},
		},
		{
			name: "chat wrong content type", bearer: fx.chatBearer, agentID: fx.agentA,
			contentType: "text/plain", body: `{}`,
			wantStatus: http.StatusUnsupportedMediaType, wantBodyParts: []string{"UNSUPPORTED_MEDIA_TYPE"},
		},
	}
}

func runChatCase(t *testing.T, fx proxyAuthFixture, tc chatCase) {
	t.Helper()
	resp, body := chatPOST(t, chatRequestOpts{
		srvURL: fx.srv.URL, bearer: tc.bearer, agentID: tc.agentID,
		contentType: tc.contentType, body: tc.body,
	})
	defer resp.Body.Close()
	if resp.StatusCode != tc.wantStatus {
		t.Fatalf("status: %d body=%s", resp.StatusCode, body)
	}
	if tc.wantBodyParts != nil {
		for _, part := range tc.wantBodyParts {
			if !strings.Contains(body, part) {
				t.Fatalf("body: %s missing %q", body, part)
			}
		}
	}
	if tc.checkHeaders {
		assertResponseHeaders(t, resp)
	}
}

func TestProxyAuthIntegration_Chat(t *testing.T) {
	fx := setupProxyAuthFixture(t)
	for _, tc := range buildChatCases(fx) {
		t.Run(tc.name, func(t *testing.T) {
			runChatCase(t, fx, tc)
		})
	}
}

func TestProxyAuthIntegration_ChatBodyTooLarge(t *testing.T) {
	fx := setupProxyAuthFixture(t)
	oversized := strings.Repeat("x", int(validation.MaxRequestBodyBytes+1))
	resp, body := chatPOST(t, chatRequestOpts{
		srvURL: fx.srv.URL, bearer: fx.chatBearer, agentID: fx.agentA,
		contentType: "application/json", body: oversized,
	})
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusRequestEntityTooLarge || !strings.Contains(body, "PAYLOAD_TOO_LARGE") {
		t.Fatalf("status: %d body=%s", resp.StatusCode, body)
	}
}
