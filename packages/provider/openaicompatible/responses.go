package openaicompatible

import (
	"context"
	"strings"

	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/packages/provider/responses"
)

// ResponsesClient is the transport seam used by the OpenAI adapter.
type ResponsesClient interface {
	CompleteResponses(context.Context, responses.Request, string, string) (provider.Response, error)
}

// CompleteResponses posts a Responses request without a custom TLS pin.
func (c *Client) CompleteResponses(ctx context.Context, req responses.Request, apiKeyOverride, baseURLOverride string) (provider.Response, error) {
	return c.CompleteResponsesWithTLS(ctx, req, apiKeyOverride, baseURLOverride, "")
}

// CompleteResponsesWithTLS posts a Responses request with tenant endpoint pinning.
func (c *Client) CompleteResponsesWithTLS(ctx context.Context, req responses.Request, apiKeyOverride, baseURLOverride, tlsServerName string) (provider.Response, error) {
	body, err := responses.MarshalRequest(req)
	if err != nil {
		return provider.Response{}, err
	}
	base := c.cfg.BaseURL
	if strings.TrimSpace(baseURLOverride) != "" {
		base = strings.TrimSpace(baseURLOverride)
	}
	spanCtx, span := provider.StartCompleteSpan(ctx, c.tracer, provider.CompleteSpan{Names: provider.CompleteSpanNames{Span: c.Name() + ".Responses", Provider: c.Name()}, Req: provider.Request{Model: req.Model, Stream: req.Stream, APIKeyOverride: apiKeyOverride, BaseURLOverride: baseURLOverride, TLSServerName: tlsServerName}})
	defer span.End()
	return c.executeWithRetry(spanCtx, span, upstreamCall{URL: provider.JoinBaseURL(base, "/responses"), Body: body, Stream: req.Stream, APIKeyOverride: apiKeyOverride, TLSServerName: tlsServerName})
}

var _ ResponsesClient = (*Client)(nil)
