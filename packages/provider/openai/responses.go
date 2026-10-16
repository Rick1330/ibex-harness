package openai

import (
	"context"
	"fmt"
	"io"

	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/packages/provider/openaicompatible"
	"github.com/Rick1330/ibex-harness/packages/provider/responses"
)

const responsesBodyLimit = 16 << 20

// CompleteResponses sends the wire request through the shared OpenAI-compatible transport.
func (c *Client) CompleteResponses(ctx context.Context, req responses.Request, apiKeyOverride, baseURLOverride string) (provider.Response, error) {
	return c.inner.CompleteResponses(ctx, req, apiKeyOverride, baseURLOverride)
}

// CreateResponse implements the typed non-streaming Responses surface.
func (c *Client) CreateResponse(ctx context.Context, req responses.Request, apiKeyOverride, baseURLOverride, tlsServerName string) (responses.Response, error) {
	if req.Stream {
		return responses.Response{}, fmt.Errorf("responses streaming is not enabled")
	}
	resp, err := c.inner.CompleteResponsesWithTLS(ctx, req, apiKeyOverride, baseURLOverride, tlsServerName)
	if err != nil {
		return responses.Response{}, err
	}
	defer func() { _ = resp.Body.Close() }()
	body, err := io.ReadAll(io.LimitReader(resp.Body, responsesBodyLimit+1))
	if err != nil {
		return responses.Response{}, err
	}
	if len(body) > responsesBodyLimit {
		return responses.Response{}, fmt.Errorf("responses provider body exceeds %d bytes", responsesBodyLimit)
	}
	return responses.ParseResponse(body)
}

var _ provider.ResponsesProvider = (*Client)(nil)
var _ openaicompatible.ResponsesClient = (*Client)(nil)
