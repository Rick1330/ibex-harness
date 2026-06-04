package llm

import "context"

type chatRequestKey struct{}

// WithChatRequest attaches a parsed chat request to the context.
func WithChatRequest(ctx context.Context, req *ChatCompletionRequest) context.Context {
	return context.WithValue(ctx, chatRequestKey{}, req)
}

// ChatRequestFromContext returns the parsed chat request when present.
func ChatRequestFromContext(ctx context.Context) (*ChatCompletionRequest, bool) {
	req, ok := ctx.Value(chatRequestKey{}).(*ChatCompletionRequest)
	return req, ok && req != nil
}
