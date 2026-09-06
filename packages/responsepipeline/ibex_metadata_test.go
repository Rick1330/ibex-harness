package responsepipeline

import (
	"context"
	"encoding/json"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/provider/mockllm"
	"github.com/stretchr/testify/require"
)

func TestUnit_SetExtra_EmbedsTopLevelKeyAndDirties(t *testing.T) {
	body := []byte(mockllm.MockJSONBody())
	resp := mustDecodeBody(t, body)
	require.NoError(t, resp.SetExtra("ibex", IbexMetadata{
		TraceID: "tr", SessionID: "sess", MemoriesInjected: 1,
		ContextTokensUsed: 2, ContextAssemblyMs: 3, ProxyOverheadMs: 4,
	}))
	out, err := resp.Bytes()
	require.NoError(t, err)
	require.NotEqual(t, body, out)

	var envelope map[string]json.RawMessage
	require.NoError(t, json.Unmarshal(out, &envelope))
	require.Contains(t, envelope, "ibex")
	require.Contains(t, envelope, "id")

	var meta IbexMetadata
	require.NoError(t, json.Unmarshal(envelope["ibex"], &meta))
	require.Equal(t, "tr", meta.TraceID)
	require.Equal(t, int32(1), meta.MemoriesInjected)
	require.Equal(t, int64(4), meta.ProxyOverheadMs)
}

func TestUnit_SetExtra_RejectsReservedAndEmpty(t *testing.T) {
	resp := mustDecodeBody(t, []byte(mockllm.MockJSONBody()))
	require.ErrorIs(t, resp.SetExtra("id", map[string]string{"x": "y"}), ErrInvalidResponse)
	require.ErrorIs(t, resp.SetExtra("", "x"), ErrInvalidResponse)
	var nilResp *ChatResponse
	require.ErrorIs(t, nilResp.SetExtra("ibex", IbexMetadata{}), ErrInvalidResponse)
}

func TestUnit_IBEXMetadataStage_NoopWithoutContext(t *testing.T) {
	body := []byte(mockllm.MockJSONBody())
	pipe := NewPipeline([]Stage{IBEXMetadataStage{}})
	require.Equal(t, body, runPipelineBytes(t, pipe, body))
}

func TestUnit_IBEXMetadataStage_EmbedsWhenPresent(t *testing.T) {
	body := []byte(mockllm.MockJSONBody())
	pipe := NewPipeline([]Stage{IBEXMetadataStage{}})
	meta := IbexMetadata{
		TraceID: "550e8400", SessionID: "7c9e6679",
		MemoriesInjected: 5, ContextTokensUsed: 1247,
		ContextAssemblyMs: 38, ProxyOverheadMs: 15,
	}
	chat := mustDecodeBody(t, body)
	out, err := pipe.Run(WithIbexMetadata(context.Background(), meta), chat)
	require.NoError(t, err)
	wire, err := out.Bytes()
	require.NoError(t, err)

	var envelope map[string]any
	require.NoError(t, json.Unmarshal(wire, &envelope))
	ibex, ok := envelope["ibex"].(map[string]any)
	require.True(t, ok)
	require.Equal(t, "550e8400", ibex["trace_id"])
	require.Equal(t, "7c9e6679", ibex["session_id"])
	require.EqualValues(t, 5, ibex["memories_injected"])
	require.EqualValues(t, 1247, ibex["context_tokens_used"])
	require.EqualValues(t, 38, ibex["context_assembly_ms"])
	require.EqualValues(t, 15, ibex["proxy_overhead_ms"])
}

func TestUnit_IBEXMetadataStage_NotSecurityCritical(t *testing.T) {
	require.False(t, isSecurityCritical(IBEXMetadataStage{}))
}
