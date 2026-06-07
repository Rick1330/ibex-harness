//go:build integration

package proxy_test

import (
	"net/http"
	"strings"
	"testing"

	"github.com/Rick1330/ibex-harness/services/proxy/internal/validation"
)

func TestProxyAuthIntegration_Chat(t *testing.T) {
	fx := setupProxyAuthFixture(t)

	t.Run("chat without permission", func(t *testing.T) {
		resp, _ := chatPOST(t, chatRequestOpts{
			srvURL: fx.srv.URL, bearer: fx.lowPermsBearer, agentID: fx.agentA,
			contentType: "application/json", body: "{}",
		})
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusForbidden {
			t.Fatalf("status: %d", resp.StatusCode)
		}
	})

	t.Run("chat stub with permission", func(t *testing.T) {
		body := `{"model":"gpt-4","messages":[{"role":"user","content":"hi"}]}`
		resp, b := chatPOST(t, chatRequestOpts{
			srvURL: fx.srv.URL, bearer: fx.chatBearer, agentID: fx.agentA,
			contentType: "application/json", body: body,
		})
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusNotImplemented {
			t.Fatalf("status: %d", resp.StatusCode)
		}
		if !strings.Contains(b, "PROVIDER_NOT_CONFIGURED") {
			t.Fatalf("body: %s", b)
		}
		assertResponseHeaders(t, resp)
	})

	t.Run("chat malformed json", func(t *testing.T) {
		resp, b := chatPOST(t, chatRequestOpts{
			srvURL: fx.srv.URL, bearer: fx.chatBearer, agentID: fx.agentA,
			contentType: "application/json", body: `{invalid`,
		})
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusBadRequest || !strings.Contains(b, "INVALID_JSON") {
			t.Fatalf("status: %d body=%s", resp.StatusCode, b)
		}
	})

	t.Run("chat missing model", func(t *testing.T) {
		body := `{"messages":[{"role":"user","content":"hi"}]}`
		resp, b := chatPOST(t, chatRequestOpts{
			srvURL: fx.srv.URL, bearer: fx.chatBearer, agentID: fx.agentA,
			contentType: "application/json", body: body,
		})
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusBadRequest {
			t.Fatalf("status: %d body=%s", resp.StatusCode, b)
		}
		if !strings.Contains(b, "VALIDATION_ERROR") || !strings.Contains(b, `"field":"model"`) {
			t.Fatalf("body: %s", b)
		}
		assertResponseHeaders(t, resp)
	})

	t.Run("chat missing agent header", func(t *testing.T) {
		body := `{"model":"gpt-4","messages":[{"role":"user","content":"hi"}]}`
		resp, b := chatPOST(t, chatRequestOpts{
			srvURL: fx.srv.URL, bearer: fx.chatBearer,
			contentType: "application/json", body: body,
		})
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusBadRequest || !strings.Contains(b, "MISSING_AGENT_ID") {
			t.Fatalf("status: %d body=%s", resp.StatusCode, b)
		}
	})

	t.Run("chat wrong content type", func(t *testing.T) {
		resp, b := chatPOST(t, chatRequestOpts{
			srvURL: fx.srv.URL, bearer: fx.chatBearer, agentID: fx.agentA,
			contentType: "text/plain", body: `{}`,
		})
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusUnsupportedMediaType || !strings.Contains(b, "UNSUPPORTED_MEDIA_TYPE") {
			t.Fatalf("status: %d body=%s", resp.StatusCode, b)
		}
	})

	t.Run("chat body too large", func(t *testing.T) {
		oversized := strings.Repeat("x", int(validation.MaxRequestBodyBytes+1))
		resp, b := chatPOST(t, chatRequestOpts{
			srvURL: fx.srv.URL, bearer: fx.chatBearer, agentID: fx.agentA,
			contentType: "application/json", body: oversized,
		})
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusRequestEntityTooLarge || !strings.Contains(b, "PAYLOAD_TOO_LARGE") {
			t.Fatalf("status: %d body=%s", resp.StatusCode, b)
		}
	})
}
