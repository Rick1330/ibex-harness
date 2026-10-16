package llm

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"strings"

	"github.com/Rick1330/ibex-harness/packages/provider/responses"
)

type responsesRequestKey struct{}

func WithResponsesRequest(ctx context.Context, req responses.Request) context.Context {
	return context.WithValue(ctx, responsesRequestKey{}, req)
}
func ResponsesRequestFromContext(ctx context.Context) (responses.Request, bool) {
	req, ok := ctx.Value(responsesRequestKey{}).(responses.Request)
	return req, ok
}

func ParseResponsesRequest(r io.Reader) (responses.Request, error) {
	dec := json.NewDecoder(r)
	dec.DisallowUnknownFields()
	var req responses.Request
	if err := dec.Decode(&req); err != nil {
		return responses.Request{}, err
	}
	var extra any
	if err := dec.Decode(&extra); err != io.EOF {
		return responses.Request{}, fmt.Errorf("trailing JSON")
	}
	req.Model = strings.TrimSpace(req.Model)
	if err := req.Validate(); err != nil {
		return responses.Request{}, err
	}
	return req, nil
}
