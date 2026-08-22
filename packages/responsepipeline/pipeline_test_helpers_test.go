package responsepipeline

import (
	"context"
	"testing"

	"github.com/stretchr/testify/require"
)

const (
	testMinimalCompletionJSON     = `{"id":"x","object":"chat.completion","choices":[]}`
	testCompletionWithModelJSON   = `{"id":"x","object":"chat.completion","choices":[],"model":"orig"}`
	testCompletionWithChoiceJSON  = `{"id":"x","object":"chat.completion","choices":[{"index":0,"message":{"role":"assistant","content":"orig"},"finish_reason":"stop"}]}`
	testCompletionWithExtraFields = `{"id":"x","object":"chat.completion","choices":[],"model":"orig","system_fingerprint":"fp","usage":{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2}}`
)

func mustDecodeBody(t *testing.T, body []byte) *ChatResponse {
	t.Helper()
	resp, err := Decode(body)
	require.NoError(t, err)
	return resp
}

func runPipelineBytes(t *testing.T, pipe *Pipeline, body []byte) []byte {
	t.Helper()
	out, err := pipe.Run(context.Background(), mustDecodeBody(t, body))
	require.NoError(t, err)
	wire, err := out.Bytes()
	require.NoError(t, err)
	return wire
}

func mustRunPipeline(t *testing.T, pipe *Pipeline, body []byte) *ChatResponse {
	t.Helper()
	out, err := pipe.Run(context.Background(), mustDecodeBody(t, body))
	require.NoError(t, err)
	return out
}

func minimalBody() []byte { return []byte(testMinimalCompletionJSON) }

func modelBody() []byte { return []byte(testCompletionWithModelJSON) }

func mutateModelStage(name, model string) stubStage {
	return stubStage{
		name: name,
		fn: func(r *ChatResponse) (*ChatResponse, error) {
			if err := r.Mutate(func(doc *ResponseDoc) error {
				doc.Model = model
				return nil
			}); err != nil {
				return nil, err
			}
			return r, nil
		},
	}
}

func orderedModelStage(name, model string, order *[]string) stubStage {
	return stubStage{
		name: name,
		fn: func(r *ChatResponse) (*ChatResponse, error) {
			*order = append(*order, name)
			return mutateModelStage(name, model).fn(r)
		},
	}
}
