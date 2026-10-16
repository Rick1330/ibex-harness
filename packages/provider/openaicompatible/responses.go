package openaicompatible

import (
	"context"
	"strings"

	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/packages/provider/responses"
)

// ResponsesClient is implemented by providers that expose the typed Responses
// endpoint. Keeping this narrow prevents Chat Completions callers from gaining
// accidental access to Responses-only fields.
type ResponsesClient interface {
	CompleteResponses(context.Context, responses.Request, string, string) (provider.Response, error)
}

// CompleteResponses posts a Responses request to /responses. The endpoint is
// intentionally opt-in and only OpenAI's native adapter implements it.
func (c *Client) CompleteResponses(ctx context.Context, req responses.Request, apiKeyOverride, baseURLOverride string) (provider.Response, error) {
	body, err := responses.MarshalRequest(req)
	if err != nil {
		return provider.Response{}, err
	}
	base := c.cfg.BaseURL
	if strings.TrimSpace(baseURLOverride) != "" {
		base = strings.TrimSpace(baseURLOverride)
	}
	spanCtx, span := provider.StartCompleteSpan(ctx, c.tracer, provider.CompleteSpan{Names: provider.CompleteSpanNames{Span: c.Name() + ".Responses", Provider: c.Name()}, Req: provider.Request{Model: req.Model, Stream: req.Stream, APIKeyOverride: apiKeyOverride, BaseURLOverride: baseURLOverride}})
	defer span.End()
	return c.executeWithRetry(spanCtx, span, upstreamCall{URL: provider.JoinBaseURL(base, "/responses"), Body: body, Stream: req.Stream, APIKeyOverride: apiKeyOverride})
}

var _ ResponsesClient = (*Client)(nil)
