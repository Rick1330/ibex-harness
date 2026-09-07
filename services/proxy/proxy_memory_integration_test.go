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

	resp, body := postMemoryChat(t, env)
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("status=%d body=%s", resp.StatusCode, body)
	}
	if !strings.Contains(body, "assistant") {
		t.Fatalf("body=%s missing assistant", body)
	}
	assertMemoryContextHeaders(t, resp, memoryContextHeaders{memories: "3", tokens: "42", fallback: "false"})
	assertInjectedAssembledMessages(t, env.provider.lastRequest().Messages)
	if got := env.server.callCount(); got != 1 {
		t.Fatalf("AssembleContext calls=%d want 1", got)
	}
}

func TestMemoryIntegration_DeadlineExceeded_FailOpen(t *testing.T) {
	runMemoryFailOpen(t, memoryFailOpenCase{
		name:     "deadline",
		timeout:  45 * time.Millisecond,
		behavior: memoryAssembleBehavior{errCode: codes.DeadlineExceeded},
	})
}

func TestMemoryIntegration_TimeoutDelay_FailOpen(t *testing.T) {
	const assembleTimeout = 25 * time.Millisecond
	runMemoryFailOpen(t, memoryFailOpenCase{
		name:    "delay",
		timeout: assembleTimeout,
		behavior: memoryAssembleBehavior{
			delay:         assembleTimeout + 80*time.Millisecond,
			defaultOKResp: true,
		},
	})
}

type memoryFailOpenCase struct {
	name     string
	timeout  time.Duration
	behavior memoryAssembleBehavior
}

func runMemoryFailOpen(t *testing.T, tc memoryFailOpenCase) {
	t.Helper()
	env := setupMemoryIntegrationEnv(t, tc.timeout)
	env.server.setBehavior(tc.behavior)

	resp, body := postMemoryChat(t, env)
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("%s: status=%d body=%s", tc.name, resp.StatusCode, body)
	}
	if got := env.server.callCount(); got != 1 {
		t.Fatalf("%s: AssembleContext calls=%d want 1", tc.name, got)
	}
	assertMemoryContextHeaders(t, resp, memoryContextHeaders{memories: "0", tokens: "0", fallback: "true"})
	assertPhase2OnlyUserMessage(t, env.provider.lastRequest().Messages)
}

func postMemoryChat(t *testing.T, env memoryIntegrationEnv) (*http.Response, string) {
	t.Helper()
	return chatPOST(t, chatRequestOpts{
		srvURL: env.proxyURL, bearer: env.chatBearer, agentID: env.agentID,
		contentType: "application/json", body: memoryIntegrationChatBody,
	})
}
