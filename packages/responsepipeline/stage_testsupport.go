package responsepipeline

import (
	"context"
	"errors"
)

// marshalFailStage forces Bytes() to fail after marking the response dirty.
// Used only by MarshalFailStageForTest; do not register in production bootstrap.
type marshalFailStage struct{}

func (marshalFailStage) Name() string { return "marshal-fail" }

func (marshalFailStage) Process(_ context.Context, resp *ChatResponse) (*ChatResponse, error) {
	cp := resp.clone()
	cp.dirty = true
	cp.errOnMarshal = errors.New("forced")
	return cp, nil
}

// MarshalFailStageForTest returns a stage that forces Bytes() marshal failure.
// Intended for unit tests only; must not be registered in production bootstrap.
func MarshalFailStageForTest() Stage { return marshalFailStage{} }
