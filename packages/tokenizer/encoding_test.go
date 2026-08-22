package tokenizer

import (
	"testing"

	tiktoken "github.com/pkoukk/tiktoken-go"
	"github.com/stretchr/testify/require"
)

func TestUnit_LoadEncoding_UnsupportedEncoding(t *testing.T) {
	_, err := loadEncoding("not-real", newBundledBpeLoader(""))
	require.Error(t, err)
	require.Contains(t, err.Error(), "unsupported encoding")
}

func TestUnit_EncodingDefinition_UsesLoaderNotGlobalCache(t *testing.T) {
	loader := newBundledBpeLoader("")
	def, err := encodingDefinition(tiktoken.MODEL_O200K_BASE, loader)
	require.NoError(t, err)
	require.NotEmpty(t, def.mergeableRanks)
	require.NotEmpty(t, def.patStr)
}

func TestUnit_LoadEncoding_BuildsWorkingTokenizer(t *testing.T) {
	tke, err := loadEncoding(tiktoken.MODEL_CL100K_BASE, newBundledBpeLoader(""))
	require.NoError(t, err)
	require.Equal(t, 2, len(tke.Encode("Hello world", nil, nil)))
}
