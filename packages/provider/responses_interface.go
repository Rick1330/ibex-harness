package provider

import (
	"context"
	"github.com/Rick1330/ibex-harness/packages/provider/responses"
)

// ResponsesProvider is intentionally optional: existing Chat Completions
// providers and test doubles remain source-compatible.
type ResponsesProvider interface {
	CreateResponse(context.Context, responses.Request) (responses.Response, error)
}
