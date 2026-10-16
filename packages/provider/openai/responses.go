package openai

import (
	"context"
	"fmt"
	"io"

	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/packages/provider/openaicompatible"
	"github.com/Rick1330/ibex-harness/packages/provider/responses"
)

func (c *Client) CompleteResponses(ctx context.Context, req responses.Request, apiKeyOverride, baseURLOverride string) (provider.Response, error) {
	return c.inner.CompleteResponses(ctx, req, apiKeyOverride, baseURLOverride)
}

// CreateResponse is the typed, non-streaming Responses surface. Streaming is
// deliberately rejected until the proxy has a semantic SSE state machine.
func (c *Client) CreateResponse(ctx context.Context, req responses.Request) (responses.Response, error) {
	if req.Stream {
		return responses.Response{}, fmt.Errorf("responses streaming is not enabled")
	}
	resp, err := c.inner.CompleteResponses(ctx, req, "", "")
	if err != nil {
		return responses.Response{}, err
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(io.LimitReader(resp.Body, 16<<20))
	if err != nil {
		return responses.Response{}, err
	}
	return responses.ParseResponse(body)
}

var _ provider.ResponsesProvider = (*Client)(nil)
var _ openaicompatible.ResponsesClient = (*Client)(nil)
