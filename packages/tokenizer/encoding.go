package tokenizer

import (
	"fmt"
	"strings"
	"sync"

	tiktoken "github.com/pkoukk/tiktoken-go"
)

var encodingLoadMu sync.Mutex

type encodingDef struct {
	name           string
	patStr         string
	mergeableRanks map[string]int
	specialTokens  map[string]int
}

func loadEncoding(enc string, loader tiktoken.BpeLoader) (*tiktoken.Tiktoken, error) {
	encodingLoadMu.Lock()
	defer encodingLoadMu.Unlock()

	def, err := encodingDefinition(enc, loader)
	if err != nil {
		return nil, err
	}
	pbe, err := tiktoken.NewCoreBPE(def.mergeableRanks, def.specialTokens, def.patStr)
	if err != nil {
		return nil, err
	}
	specialTokensSet := make(map[string]any, len(def.specialTokens))
	for token := range def.specialTokens {
		specialTokensSet[token] = true
	}
	encObj := &tiktoken.Encoding{
		Name:           def.name,
		PatStr:         def.patStr,
		MergeableRanks: def.mergeableRanks,
		SpecialTokens:  def.specialTokens,
	}
	return tiktoken.NewTiktoken(pbe, encObj, specialTokensSet), nil
}

func encodingDefinition(name string, loader tiktoken.BpeLoader) (*encodingDef, error) {
	switch name {
	case tiktoken.MODEL_O200K_BASE:
		return loadO200kDefinition(loader)
	case tiktoken.MODEL_CL100K_BASE:
		return loadCL100kDefinition(loader)
	default:
		return nil, fmt.Errorf("unsupported encoding %q", name)
	}
}

func loadO200kDefinition(loader tiktoken.BpeLoader) (*encodingDef, error) {
	ranks, err := loader.LoadTiktokenBpe("o200k_base.tiktoken")
	if err != nil {
		return nil, err
	}
	return &encodingDef{
		name:           tiktoken.MODEL_O200K_BASE,
		mergeableRanks: ranks,
		specialTokens: map[string]int{
			tiktoken.ENDOFTEXT:   199999,
			tiktoken.ENDOFPROMPT: 200018,
		},
		patStr: strings.Join([]string{
			`[^\r\n\p{L}\p{N}]?[\p{Lu}\p{Lt}\p{Lm}\p{Lo}\p{M}]*[\p{Ll}\p{Lm}\p{Lo}\p{M}]+(?i:'s|'t|'re|'ve|'m|'ll|'d)?`,
			`[^\r\n\p{L}\p{N}]?[\p{Lu}\p{Lt}\p{Lm}\p{Lo}\p{M}]+[\p{Ll}\p{Lm}\p{Lo}\p{M}]*(?i:'s|'t|'re|'ve|'m|'ll|'d)?`,
			`\p{N}{1,3}`,
			` ?[^\s\p{L}\p{N}]+[\r\n/]*`,
			`\s*[\r\n]+`,
			`\s+(?!\S)`,
			`\s+`,
		}, "|"),
	}, nil
}

func loadCL100kDefinition(loader tiktoken.BpeLoader) (*encodingDef, error) {
	ranks, err := loader.LoadTiktokenBpe("cl100k_base.tiktoken")
	if err != nil {
		return nil, err
	}
	return &encodingDef{
		name:           tiktoken.MODEL_CL100K_BASE,
		mergeableRanks: ranks,
		specialTokens: map[string]int{
			tiktoken.ENDOFTEXT:   100257,
			tiktoken.FIM_PREFIX:  100258,
			tiktoken.FIM_MIDDLE:  100259,
			tiktoken.FIM_SUFFIX:  100260,
			tiktoken.ENDOFPROMPT: 100276,
		},
		patStr: `(?i:'s|'t|'re|'ve|'m|'ll|'d)|[^\r\n\p{L}\p{N}]?\p{L}+|\p{N}{1,3}| ?[^\s\p{L}\p{N}]+[\r\n]*|\s*[\r\n]+|\s+(?!\S)|\s+`,
	}, nil
}
