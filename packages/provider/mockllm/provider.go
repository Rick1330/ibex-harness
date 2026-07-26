// Package mockllm provides an in-process LLM provider for CI and local smoke.
// Complete returns a tiny OpenAI-shaped body immediately (no network).
package mockllm

import (
	"context"
	"io"
	"net/http"
	"strings"

	"github.com/Rick1330/ibex-harness/packages/provider"
)

const mockJSONBody = `{"id":"mock","object":"chat.completion","choices":[{"index":0,"message":{"role":"assistant","content":"ok"},"finish_reason":"stop"}],"usage":{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2}}`

// Minimal OpenAI-shaped SSE so stream=true clients get a valid event stream.
const mockSSEBody = "data: {\"id\":\"mock\",\"object\":\"chat.completion.chunk\",\"choices\":[{\"index\":0,\"delta\":{\"content\":\"ok\"},\"finish_reason\":null}]}\n\ndata: [DONE]\n\n"

// Provider implements provider.Provider with zero upstream latency.
type Provider struct{}

// Name returns the provider identifier.
func (Provider) Name() string { return "mock" }

// SupportedModels mirrors the OpenAI model IDs used in Phase 2 routing.
func (Provider) SupportedModels() []string {
	return []string{"gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"}
}

// Complete returns an immediate success response.
// Non-stream requests get JSON; stream=true gets a minimal SSE frame + [DONE].
func (Provider) Complete(_ context.Context, req provider.Request) (provider.Response, error) {
	body := mockJSONBody
	if req.Stream {
		body = mockSSEBody
	}
	return provider.Response{
		StatusCode: http.StatusOK,
		Body:       io.NopCloser(strings.NewReader(body)),
		Usage:      &provider.Usage{InputTokens: 1, OutputTokens: 1, TotalTokens: 2},
	}, nil
}
