package tokenizer

import (
	"errors"
	"testing"

	tiktoken "github.com/pkoukk/tiktoken-go"
	"github.com/stretchr/testify/require"
)

type failBpeLoader struct{}

func (failBpeLoader) LoadTiktokenBpe(string) (map[string]int, error) {
	return nil, errors.New("bpe load failed")
}

func TestUnit_LoadEncoding_UnsupportedEncoding(t *testing.T) {
	_, err := loadEncoding("not-real", newBundledBpeLoader(assetDirPath("")))
	require.Error(t, err)
	require.Contains(t, err.Error(), "unsupported encoding")
}

func TestUnit_EncodingDefinition_UsesLoaderNotGlobalCache(t *testing.T) {
	loader := newBundledBpeLoader(assetDirPath(""))
	def, err := encodingDefinition(tiktoken.MODEL_O200K_BASE, loader)
	require.NoError(t, err)
	require.NotEmpty(t, def.mergeableRanks)
	require.NotEmpty(t, def.patStr)
}

func TestUnit_LoadEncoding_BuildsWorkingTokenizer(t *testing.T) {
	tke, err := loadEncoding(tiktoken.MODEL_CL100K_BASE, newBundledBpeLoader(assetDirPath("")))
	require.NoError(t, err)
	require.Equal(t, 2, len(tke.Encode(VectorHelloWorld(), nil, nil)))
}

func TestUnit_LoadO200kDefinition_PropagatesLoaderError(t *testing.T) {
	_, err := loadO200kDefinition(failBpeLoader{})
	require.Error(t, err)
	require.Contains(t, err.Error(), "bpe load failed")
}

func TestUnit_LoadCL100kDefinition_PropagatesLoaderError(t *testing.T) {
	_, err := loadCL100kDefinition(failBpeLoader{})
	require.Error(t, err)
}

func TestUnit_LoadEncoding_PropagatesDefinitionError(t *testing.T) {
	_, err := loadEncoding(tiktoken.MODEL_CL100K_BASE, failBpeLoader{})
	require.Error(t, err)
}
