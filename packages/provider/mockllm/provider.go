// Package mockllm provides an in-process LLM provider for CI and local smoke.
// Complete returns a tiny OpenAI-shaped JSON body immediately (no network).
package mockllm

import (
	"context"
	"io"
	"net/http"
	"strings"

	"github.com/Rick1330/ibex-harness/packages/provider"
)

const mockBody = `{"id":"mock","object":"chat.completion","choices":[{"index":0,"message":{"role":"assistant","content":"ok"},"finish_reason":"stop"}],"usage":{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2}}`

// Provider implements provider.Provider with zero upstream latency.
type Provider struct{}

// Name returns the provider identifier.
func (Provider) Name() string { return "mock" }

// SupportedModels mirrors the OpenAI model IDs used in Phase 2 routing.
func (Provider) SupportedModels() []string {
	return []string{"gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"}
}

// Complete returns an immediate success response. Stream requests get the same
// JSON body (non-SSE); benchmarks and k6 use stream=false.
func (Provider) Complete(_ context.Context, _ provider.Request) (provider.Response, error) {
	return provider.Response{
		StatusCode: http.StatusOK,
		Body:       io.NopCloser(strings.NewReader(mockBody)),
		Usage:      &provider.Usage{InputTokens: 1, OutputTokens: 1, TotalTokens: 2},
	}, nil
}
