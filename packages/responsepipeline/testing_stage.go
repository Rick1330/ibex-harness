package responsepipeline

import "context"

// ForceBytesErrorStage is a test-only stage that forces Bytes() to fail after marking dirty.
type ForceBytesErrorStage struct{}

func (ForceBytesErrorStage) Name() string { return "force-bytes-error" }

func (ForceBytesErrorStage) Process(_ context.Context, resp *ChatResponse) (*ChatResponse, error) {
	cp := resp.clone()
	cp.dirty = true
	cp.forceBytesErr = true
	return cp, nil
}
