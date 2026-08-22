package tokenizer

import (
	_ "embed"
	"encoding/base64"
	"errors"
	"fmt"
	"io"
	"io/fs"
	"os"
	"path"
	"strconv"
	"strings"

	"github.com/pkoukk/tiktoken-go"
	tiktoken_loader "github.com/pkoukk/tiktoken-go-loader"
)

// embed is required so o200k_base.tiktoken ships in the binary for air-gap installs.
//
//go:embed assets/o200k_base.tiktoken
var embeddedO200kBPE []byte

const maxBpeAssetBytes = 64 << 20 // 64 MiB cap for operator-supplied override files

// ErrAssetPathEscape is returned when a resolved asset path leaves IBEX_TOKENIZER_ASSET_DIR.
var ErrAssetPathEscape = errors.New("tokenizer asset path escapes asset dir")

// ErrAssetSymlink is returned when a tokenizer asset path is a symbolic link.
var ErrAssetSymlink = errors.New("tokenizer asset is a symbolic link")

// ErrAssetNotRegular is returned when a tokenizer asset is not a regular file.
var ErrAssetNotRegular = errors.New("tokenizer asset is not a regular file")

var (
	errInvalidBpeLine     = errors.New("invalid bpe line")
	errEmptyBpeVocab      = errors.New("empty bpe vocabulary")
	errDuplicateBpeToken  = errors.New("duplicate bpe token")
	errDuplicateBpeRank   = errors.New("duplicate bpe rank")
	errNegativeBpeRank    = errors.New("negative bpe rank")
	errNonContiguousRanks = errors.New("non-contiguous bpe ranks")
)

type bundledBpeLoader struct {
	assetDir assetDirPath
	offline  tiktoken.BpeLoader
}

func newBundledBpeLoader(assetDir assetDirPath) *bundledBpeLoader {
	return &bundledBpeLoader{
		assetDir: assetDirPath(strings.TrimSpace(string(assetDir))),
		offline:  tiktoken_loader.NewOfflineLoader(),
	}
}

func (l *bundledBpeLoader) LoadTiktokenBpe(tiktokenBpeFile string) (map[string]int, error) {
	base := path.Base(tiktokenBpeFile)
	if l.assetDir != "" {
		ranks, found, err := loadBpeFromAssetDir(l.assetDir, assetBasename(base))
		if err != nil {
			return nil, err
		}
		if found {
			return ranks, nil
		}
	}
	if base == "o200k_base.tiktoken" {
		return parseBpeLines(bpeVocabText(embeddedO200kBPE))
	}
	return l.offline.LoadTiktokenBpe(tiktokenBpeFile)
}

func loadBpeFromAssetDir(assetDir assetDirPath, base assetBasename) (map[string]int, bool, error) {
	ref, err := jailedAssetLocation(assetDir, base)
	if err != nil {
		return nil, false, err
	}
	assetRoot, err := os.OpenRoot(string(ref.root))
	if err != nil {
		return nil, false, err
	}
	defer func() { _ = assetRoot.Close() }()

	f, found, err := openJailedAssetFile(assetRoot, ref)
	if err != nil || !found {
		return nil, found, err
	}
	defer func() { _ = f.Close() }()

	raw, err := readBoundedFile(f, maxBpeAssetBytes)
	if err != nil {
		return nil, true, err
	}
	ranks, err := parseBpeLines(bpeVocabText(raw))
	return ranks, true, err
}

func openJailedAssetFile(assetRoot *os.Root, ref jailedAssetRef) (*os.File, bool, error) {
	name := string(ref.basename)
	info, err := assetRoot.Lstat(name)
	if err != nil {
		if errors.Is(err, fs.ErrNotExist) {
			return nil, false, nil
		}
		return nil, false, err
	}
	if err := rejectNonRegularAsset(info, ref.basename); err != nil {
		return nil, true, err
	}

	f, err := assetRoot.OpenFile(name, os.O_RDONLY|openFlagNoFollow(), 0)
	if err != nil {
		return nil, true, err
	}
	st, err := f.Stat()
	if err != nil {
		_ = f.Close()
		return nil, true, err
	}
	if err := rejectNonRegularAsset(st, ref.basename); err != nil {
		_ = f.Close()
		return nil, true, err
	}
	return f, true, nil
}

func rejectNonRegularAsset(info fs.FileInfo, label assetBasename) error {
	if info.Mode()&os.ModeSymlink != 0 {
		return fmt.Errorf("%w: %q", ErrAssetSymlink, label)
	}
	if !info.Mode().IsRegular() {
		return fmt.Errorf("%w: %q", ErrAssetNotRegular, label)
	}
	return nil
}

func readBoundedFile(r io.Reader, maxBytes int64) ([]byte, error) {
	limited := io.LimitReader(r, maxBytes+1)
	raw, err := io.ReadAll(limited)
	if err != nil {
		return nil, err
	}
	if int64(len(raw)) > maxBytes {
		return nil, fmt.Errorf("bpe asset exceeds %d bytes", maxBytes)
	}
	return raw, nil
}

func readBoundedFSFile(fsys fs.FS, name assetBasename, maxBytes int64) ([]byte, error) {
	f, err := fsys.Open(string(name))
	if err != nil {
		return nil, err
	}
	defer func() { _ = f.Close() }()
	return readBoundedFile(f, maxBytes)
}

type bpeVocabText []byte

func (t bpeVocabText) string() string { return string(t) }

func parseBpeLines(contents bpeVocabText) (map[string]int, error) {
	if strings.TrimSpace(contents.string()) == "" {
		return nil, errEmptyBpeVocab
	}
	bpeRanks := make(map[string]int)
	seenRanks := make(map[int]struct{})
	lineNo := 0
	for _, line := range strings.Split(contents.string(), "\n") {
		if line == "" {
			continue
		}
		lineNo++
		if err := addBpeLine(bpeRanks, seenRanks, bpeInputLine{no: lineNo, text: bpeLineText(line)}); err != nil {
			return nil, err
		}
	}
	if len(bpeRanks) == 0 {
		return nil, errEmptyBpeVocab
	}
	if err := validateContiguousRanks(seenRanks, len(bpeRanks)); err != nil {
		return nil, err
	}
	return bpeRanks, nil
}

type bpeLineText string

type bpeInputLine struct {
	no   int
	text bpeLineText
}

type bpeToken struct {
	value string
	rank  int
}

func addBpeLine(bpeRanks map[string]int, seenRanks map[int]struct{}, line bpeInputLine) error {
	token, err := parseBpeLine(line.text)
	if err != nil {
		return fmt.Errorf("line %d: %w", line.no, err)
	}
	if _, dup := bpeRanks[token.value]; dup {
		return fmt.Errorf("line %d: %w", line.no, errDuplicateBpeToken)
	}
	if _, dup := seenRanks[token.rank]; dup {
		return fmt.Errorf("line %d: %w", line.no, errDuplicateBpeRank)
	}
	if token.rank < 0 {
		return fmt.Errorf("line %d: %w", line.no, errNegativeBpeRank)
	}
	bpeRanks[token.value] = token.rank
	seenRanks[token.rank] = struct{}{}
	return nil
}

func parseBpeLine(line bpeLineText) (bpeToken, error) {
	parts := strings.Split(string(line), " ")
	if len(parts) != 2 {
		return bpeToken{}, errInvalidBpeLine
	}
	decoded, err := base64.StdEncoding.DecodeString(parts[0])
	if err != nil {
		return bpeToken{}, err
	}
	rank, err := strconv.Atoi(parts[1])
	if err != nil {
		return bpeToken{}, err
	}
	return bpeToken{value: string(decoded), rank: rank}, nil
}

func validateContiguousRanks(seen map[int]struct{}, count int) error {
	for i := 0; i < count; i++ {
		if _, ok := seen[i]; !ok {
			return errNonContiguousRanks
		}
	}
	return nil
}
