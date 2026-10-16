package provider

import (
	"context"
	"github.com/Rick1330/ibex-harness/packages/provider/responses"
)

// ResponsesProvider is optional so existing Chat-only providers remain compatible.
type ResponsesProvider interface {
	// CreateResponse sends one non-streaming Responses request using per-request credential overrides.
	CreateResponse(context.Context, responses.Request, string, string, string) (responses.Response, error)
}
