package tokenizer

import (
	_ "embed"
	"encoding/base64"
	"errors"
	"fmt"
	"os"
	"path"
	"path/filepath"
	"strconv"
	"strings"

	"github.com/pkoukk/tiktoken-go"
	tiktoken_loader "github.com/pkoukk/tiktoken-go-loader"
)

//go:embed assets/o200k_base.tiktoken
var embeddedO200kBPE []byte

// ErrAssetPathEscape is returned when a resolved asset path leaves IBEX_TOKENIZER_ASSET_DIR.
var ErrAssetPathEscape = errors.New("tokenizer asset path escapes asset dir")

type bundledBpeLoader struct {
	assetDir string
	offline  tiktoken.BpeLoader
}

func newBundledBpeLoader(assetDir string) *bundledBpeLoader {
	return &bundledBpeLoader{
		assetDir: strings.TrimSpace(assetDir),
		offline:  tiktoken_loader.NewOfflineLoader(),
	}
}

func (l *bundledBpeLoader) LoadTiktokenBpe(tiktokenBpeFile string) (map[string]int, error) {
	base := path.Base(tiktokenBpeFile)
	if l.assetDir != "" {
		ranks, found, err := loadBpeFromAssetDir(l.assetDir, base)
		if err != nil {
			return nil, err
		}
		if found {
			return ranks, nil
		}
	}
	if base == "o200k_base.tiktoken" {
		return parseBpeLines(string(embeddedO200kBPE))
	}
	return l.offline.LoadTiktokenBpe(tiktokenBpeFile)
}

func loadBpeFromAssetDir(assetDir, base string) (map[string]int, bool, error) {
	target, err := jailedAssetPath(assetDir, base)
	if err != nil {
		return nil, false, err
	}
	if _, err := os.Stat(target); err != nil {
		if os.IsNotExist(err) {
			return nil, false, nil
		}
		return nil, false, err
	}
	ranks, err := loadBpeFile(target)
	return ranks, true, err
}

func jailedAssetPath(assetDir, base string) (string, error) {
	if strings.TrimSpace(base) == "" || base != path.Base(base) || strings.Contains(base, string(os.PathSeparator)) {
		return "", fmt.Errorf("%w: invalid asset basename %q", ErrAssetPathEscape, base)
	}
	root, err := filepath.Abs(filepath.Clean(assetDir))
	if err != nil {
		return "", err
	}
	target, err := filepath.Abs(filepath.Join(root, base))
	if err != nil {
		return "", err
	}
	rel, err := filepath.Rel(root, target)
	if err != nil || strings.HasPrefix(rel, "..") {
		return "", fmt.Errorf("%w: %q", ErrAssetPathEscape, base)
	}
	return target, nil
}

func loadBpeFile(path string) (map[string]int, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	return parseBpeLines(string(raw))
}

func parseBpeLines(contents string) (map[string]int, error) {
	bpeRanks := make(map[string]int)
	for _, line := range strings.Split(contents, "\n") {
		if line == "" {
			continue
		}
		parts := strings.Split(line, " ")
		if len(parts) != 2 {
			return nil, fmt.Errorf("invalid bpe line")
		}
		token, err := base64.StdEncoding.DecodeString(parts[0])
		if err != nil {
			return nil, err
		}
		rank, err := strconv.Atoi(parts[1])
		if err != nil {
			return nil, err
		}
		bpeRanks[string(token)] = rank
	}
	return bpeRanks, nil
}
