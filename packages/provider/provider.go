// Package provider defines the LLM provider abstraction for IBEX Harness.
// All LLM communication goes through this interface.
//
// Phase 2: OpenAI implementation only.
// Phase 4: Anthropic, Azure OpenAI, AWS Bedrock implementations added.
package provider

import (
	"context"
	"io"
	"time"
)

// Request is a normalised LLM completion request.
// It is provider-agnostic; implementations translate to provider-specific format.
// Directive injection (Phase 2.3.3) mutates Messages before Complete is called.
type Request struct {
	// Model is the model identifier as requested by the client.
	Model string

	// Messages is the conversation history (including any injected directive).
	Messages []Message

	// Stream, if true, requests a streaming (SSE) response.
	Stream bool

	// MaxTokens is the maximum number of completion tokens. 0 = provider default.
	MaxTokens int

	// Temperature controls randomness. Nil = provider default.
	Temperature *float64

	// PassthroughFields contains client-supplied fields not explicitly modelled.
	PassthroughFields map[string]any
}

// Message is a single turn in the conversation.
type Message struct {
	Role    string // "system", "user", "assistant", "tool"
	Content string
}

// Response is the outcome of a Complete call.
// For non-streaming requests, Body contains the complete provider JSON response.
// For streaming requests, Body is an SSE stream; the caller must read and forward it.
// The caller is responsible for closing Body.
type Response struct {
	// Body is the response body from the provider.
	Body io.ReadCloser

	// StatusCode is the provider HTTP response status code.
	StatusCode int

	// Usage holds token counts extracted from the response.
	Usage *Usage

	// Latency is the time from sending the request to receiving the first byte.
	Latency time.Duration

	// ProviderRequestID is the request ID returned by the provider.
	ProviderRequestID string
}

// Usage holds LLM token consumption data.
type Usage struct {
	InputTokens  int
	OutputTokens int
	TotalTokens  int
}

// Provider is the interface all LLM provider implementations must satisfy.
// Implementations must be safe for concurrent use.
type Provider interface {
	// Complete sends a request to the LLM provider and returns the response.
	Complete(ctx context.Context, req Request) (Response, error)

	// Name returns the provider identifier (e.g. "openai", "anthropic").
	Name() string

	// SupportedModels returns the list of model IDs this provider handles.
	SupportedModels() []string
}
