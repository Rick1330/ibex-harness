package http

import (
	"errors"
	"net/http"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/packages/permissions"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/packages/ratelimit"
	"github.com/Rick1330/ibex-harness/packages/telemetry"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
)

func TestUnit_ChatCompletions_EmitsTraceOnSuccess(t *testing.T) {
	t.Parallel()
	tw := &recordingTraceWriter{}
	handler := chatRouterWithTrace(t, tw, mustPool(t))
	rec := postChat(t, handler, chatRequestOpts{
		body: `{"model":"gpt-4o","messages":[{"role":"user","content":"hi"}]}`,
		auth: true, agentID: testChatAgentID,
	})
	assertStatusOK(t, rec.Code)
	tw.waitWrites(t, 1)
	got, ok := tw.last()
	if !ok {
		t.Fatal("no write")
	}
	if got.Provider != "openai" {
		t.Fatalf("provider=%s", got.Provider)
	}
	if got.Model != "gpt-4o" {
		t.Fatalf("model=%s", got.Model)
	}
}

func TestUnit_ChatCompletions_EmitsTraceOnProviderFailure(t *testing.T) {
	t.Parallel()
	tw := &recordingTraceWriter{}
	reg, err := provider.NewRegistry(stubLLMProvider{
		name: "openai", models: []string{"gpt-4o"},
		err: &provider.ProviderError{ProviderName: "openai", StatusCode: http.StatusBadGateway},
	})
	if err != nil {
		t.Fatal(err)
	}
	handler := mustNewRouter(t, RouterDeps{
		Config: chatTestConfig(), Logger: logger.Discard("proxy"),
		Metrics: metrics.NewProxy("test"), Tracer: telemetry.NoopTracer("proxy"),
		Validator: &chatMockValidator{res: &auth.ValidateResult{
			OrgID: testChatOrgID, Permissions: permissions.ProxyChatCompletion,
		}},
		AgentVerifier: passAgentVerifier{}, Limiter: ratelimit.Noop(),
		CheckpointPool: mustPool(t), TraceWriter: tw,
		Health: testHealthServer(), ProviderRegistry: reg,
	})
	rec := postChat(t, handler, chatRequestOpts{
		body: `{"model":"gpt-4o","stream":true,"messages":[{"role":"user","content":"hi"}]}`,
		auth: true, agentID: testChatAgentID,
	})
	if rec.Code == http.StatusOK {
		t.Fatal("expected provider failure status")
	}
	tw.waitWrites(t, 1)
	got, ok := tw.last()
	if !ok {
		t.Fatal("no write")
	}
	if got.IsComplete {
		t.Fatal("expected incomplete")
	}
	if got.ErrorCode == "" {
		t.Fatal("expected error_code")
	}
	if !got.IsStreaming {
		t.Fatal("stream failure should set is_streaming on trace")
	}
}

func TestUnit_ChatCompletions_WriteErrorKeepsHTTPOK(t *testing.T) {
	t.Parallel()
	tw := &recordingTraceWriter{err: errors.New("flush fail")}
	handler := chatRouterWithTrace(t, tw, mustPool(t))
	rec := postChat(t, handler, chatRequestOpts{
		body: `{"model":"gpt-4o","messages":[{"role":"user","content":"hi"}]}`,
		auth: true, agentID: testChatAgentID,
	})
	assertStatusOK(t, rec.Code)
	tw.waitWrites(t, 1)
}
