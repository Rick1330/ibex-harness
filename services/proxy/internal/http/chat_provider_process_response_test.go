package http

import (
	"testing"

	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/packages/responsepipeline"
	"github.com/stretchr/testify/require"
)

func TestUnit_processResponseBody_serializeErrorMessage(t *testing.T) {
	t.Parallel()
	body := []byte(`{"id":"x","object":"chat.completion","choices":[]}`)
	h := chatCompletionHandler{
		responsePipeline: responsepipeline.NewPipeline([]responsepipeline.Stage{responsepipeline.MarshalFailStageForTest()}),
	}
	_, err := h.processResponseBody(t.Context(), "openai", body)
	require.Error(t, err)
	var pe *provider.ProviderError
	require.ErrorAs(t, err, &pe)
	require.Equal(t, errMsgResponsePipelineSerialize, pe.ProviderErrMsg)
}
