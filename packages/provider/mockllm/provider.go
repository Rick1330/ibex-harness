// Package mockllm provides an in-process LLM provider for CI and local smoke.
// It never opens a network connection: Complete always returns a deterministic
// OpenAI-shaped body immediately.
package mockllm

import (
	"context"
	"io"
	"net/http"
	"strings"

	"github.com/Rick1330/ibex-harness/packages/provider"
)

const mockJSONBody = `{"id":"mock","object":"chat.completion","choices":[{"index":0,"message":{"role":"assistant","content":"ok"},"finish_reason":"stop"}],"usage":{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2}}`

// MockJSONBody returns the deterministic non-stream JSON body used by mockllm.Provider.
func MockJSONBody() string { return mockJSONBody }

// Minimal OpenAI-shaped SSE so stream=true clients get a valid event stream.
const mockSSEBody = "data: {\"id\":\"mock\",\"object\":\"chat.completion.chunk\",\"choices\":[{\"index\":0,\"delta\":{\"content\":\"ok\"},\"finish_reason\":null}]}\n\ndata: [DONE]\n\n"

// Provider implements provider.Provider with zero upstream latency.
// The zero value is ready to use; Name/SupportedModels/Complete never return
// errors for valid in-process construction (no I/O, no config).
type Provider struct{}

// Name returns the provider identifier ("mock").
func (Provider) Name() string { return "mock" }

// SupportedModels lists the Phase 2 OpenAI model IDs this stub accepts so
// provider.Registry routing matches live OpenAI registrations in tests/CI.
func (Provider) SupportedModels() []string {
	return []string{"gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"}
}

// Complete returns an immediate HTTP 200 success response.
// Non-stream requests get a chat.completion JSON body; stream=true gets a
// minimal SSE frame ending with [DONE]. Complete never returns an error.
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
