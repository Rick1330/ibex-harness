//go:build integration

package proxy_test

import (
	"net/http"
	"strings"
	"testing"
	"time"

	"google.golang.org/grpc/codes"
)

func TestMemoryIntegration_AssembleSuccess(t *testing.T) {
	env := setupMemoryIntegrationEnv(t, 45*time.Millisecond)
	env.server.setBehavior(memoryAssembleBehavior{defaultOKResp: true})

	resp, body := chatPOST(t, chatRequestOpts{
		srvURL: env.proxyURL, bearer: env.chatBearer, agentID: env.agentID,
		contentType: "application/json", body: memoryIntegrationChatBody,
	})
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("status=%d body=%s", resp.StatusCode, body)
	}
	if !strings.Contains(body, "assistant") {
		t.Fatalf("body=%s missing assistant", body)
	}
	assertMemoryContextHeaders(t, resp, "3", "42", "false")
	assertInjectedAssembledMessages(t, env.provider.lastRequest().Messages)
	if env.server.callCount() < 1 {
		t.Fatal("expected AssembleContext call")
	}
}

func TestMemoryIntegration_DeadlineExceeded_FailOpen(t *testing.T) {
	env := setupMemoryIntegrationEnv(t, 45*time.Millisecond)
	env.server.setBehavior(memoryAssembleBehavior{errCode: codes.DeadlineExceeded})

	resp, body := chatPOST(t, chatRequestOpts{
		srvURL: env.proxyURL, bearer: env.chatBearer, agentID: env.agentID,
		contentType: "application/json", body: memoryIntegrationChatBody,
	})
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("status=%d body=%s", resp.StatusCode, body)
	}
	assertMemoryContextHeaders(t, resp, "0", "0", "true")
	assertPhase2OnlyUserMessage(t, env.provider.lastRequest().Messages)
}

func TestMemoryIntegration_TimeoutDelay_FailOpen(t *testing.T) {
	const assembleTimeout = 25 * time.Millisecond
	env := setupMemoryIntegrationEnv(t, assembleTimeout)
	// Sleep past the client deadline, then would succeed — real WithTimeout fail-open.
	env.server.setBehavior(memoryAssembleBehavior{
		delay:         assembleTimeout + 80*time.Millisecond,
		defaultOKResp: true,
	})

	resp, body := chatPOST(t, chatRequestOpts{
		srvURL: env.proxyURL, bearer: env.chatBearer, agentID: env.agentID,
		contentType: "application/json", body: memoryIntegrationChatBody,
	})
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("status=%d body=%s", resp.StatusCode, body)
	}
	assertMemoryContextHeaders(t, resp, "0", "0", "true")
	assertPhase2OnlyUserMessage(t, env.provider.lastRequest().Messages)
}
