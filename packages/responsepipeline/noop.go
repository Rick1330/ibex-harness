package responsepipeline

import "context"

// NoopStage is the default identity stage (production default).
type NoopStage struct{}

func (NoopStage) Name() string { return "noop" }

func (NoopStage) Process(_ context.Context, resp *ChatResponse) (*ChatResponse, error) {
	return resp, nil
}
