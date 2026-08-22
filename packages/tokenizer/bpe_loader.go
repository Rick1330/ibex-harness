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
	"path/filepath"
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
	safeBase, root, err := jailedAssetLocation(assetDir, base)
	if err != nil {
		return nil, false, err
	}
	assetRoot, err := os.OpenRoot(root)
	if err != nil {
		return nil, false, err
	}
	defer assetRoot.Close()

	f, found, err := openJailedAssetFile(assetRoot, safeBase)
	if err != nil || !found {
		return nil, found, err
	}
	defer func() { _ = f.Close() }()

	raw, err := readBoundedFile(f, maxBpeAssetBytes)
	if err != nil {
		return nil, true, err
	}
	ranks, err := parseBpeLines(string(raw))
	return ranks, true, err
}

func openJailedAssetFile(assetRoot *os.Root, safeBase string) (*os.File, bool, error) {
	info, err := assetRoot.Lstat(safeBase)
	if err != nil {
		if errors.Is(err, fs.ErrNotExist) {
			return nil, false, nil
		}
		return nil, false, err
	}
	if err := rejectNonRegularAsset(info, safeBase); err != nil {
		return nil, true, err
	}

	f, err := assetRoot.OpenFile(safeBase, os.O_RDONLY|openFlagNoFollow(), 0)
	if err != nil {
		return nil, true, err
	}
	st, err := f.Stat()
	if err != nil {
		_ = f.Close()
		return nil, true, err
	}
	if err := rejectNonRegularAsset(st, safeBase); err != nil {
		_ = f.Close()
		return nil, true, err
	}
	return f, true, nil
}

func rejectNonRegularAsset(info fs.FileInfo, label string) error {
	if info.Mode()&os.ModeSymlink != 0 {
		return fmt.Errorf("%w: %q", ErrAssetSymlink, label)
	}
	if !info.Mode().IsRegular() {
		return fmt.Errorf("%w: %q", ErrAssetNotRegular, label)
	}
	return nil
}

func jailedAssetPath(assetDir, base string) (string, error) {
	safeBase, root, err := jailedAssetLocation(assetDir, base)
	if err != nil {
		return "", err
	}
	return filepath.Join(root, safeBase), nil
}

func jailedAssetLocation(assetDir, base string) (safeBase, root string, err error) {
	safeBase, err = sanitizeAssetBasename(base)
	if err != nil {
		return "", "", err
	}
	root, err = filepath.Abs(filepath.Clean(assetDir))
	if err != nil {
		return "", "", err
	}
	resolved := filepath.Join(root, safeBase)
	if err := assertPathUnderRoot(root, resolved, safeBase); err != nil {
		return "", "", err
	}
	return safeBase, root, nil
}

func assertPathUnderRoot(root, resolved, label string) error {
	rel, err := filepath.Rel(root, resolved)
	if err != nil || strings.HasPrefix(rel, "..") {
		return fmt.Errorf("%w: %q", ErrAssetPathEscape, label)
	}
	return nil
}

func sanitizeAssetBasename(base string) (string, error) {
	trimmed := strings.TrimSpace(base)
	if trimmed == "" {
		return "", fmt.Errorf("%w: invalid asset basename %q", ErrAssetPathEscape, base)
	}
	if trimmed != path.Base(trimmed) {
		return "", fmt.Errorf("%w: invalid asset basename %q", ErrAssetPathEscape, base)
	}
	if strings.Contains(trimmed, string(os.PathSeparator)) {
		return "", fmt.Errorf("%w: invalid asset basename %q", ErrAssetPathEscape, base)
	}
	return trimmed, nil
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

func readBoundedFSFile(fsys fs.FS, name string, maxBytes int64) ([]byte, error) {
	f, err := fsys.Open(name)
	if err != nil {
		return nil, err
	}
	defer func() { _ = f.Close() }()
	return readBoundedFile(f, maxBytes)
}

func parseBpeLines(contents string) (map[string]int, error) {
	if strings.TrimSpace(contents) == "" {
		return nil, errEmptyBpeVocab
	}
	bpeRanks := make(map[string]int)
	seenRanks := make(map[int]struct{})
	lineNo := 0
	for _, line := range strings.Split(contents, "\n") {
		if line == "" {
			continue
		}
		lineNo++
		if err := addBpeLine(bpeRanks, seenRanks, lineNo, line); err != nil {
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

func addBpeLine(bpeRanks map[string]int, seenRanks map[int]struct{}, lineNo int, line string) error {
	token, rank, err := parseBpeLine(line)
	if err != nil {
		return fmt.Errorf("line %d: %w", lineNo, err)
	}
	if _, dup := bpeRanks[token]; dup {
		return fmt.Errorf("line %d: %w", lineNo, errDuplicateBpeToken)
	}
	if _, dup := seenRanks[rank]; dup {
		return fmt.Errorf("line %d: %w", lineNo, errDuplicateBpeRank)
	}
	if rank < 0 {
		return fmt.Errorf("line %d: %w", lineNo, errNegativeBpeRank)
	}
	bpeRanks[token] = rank
	seenRanks[rank] = struct{}{}
	return nil
}

func parseBpeLine(line string) (token string, rank int, err error) {
	parts := strings.Split(line, " ")
	if len(parts) != 2 {
		return "", 0, errInvalidBpeLine
	}
	decoded, err := base64.StdEncoding.DecodeString(parts[0])
	if err != nil {
		return "", 0, err
	}
	rank, err = strconv.Atoi(parts[1])
	if err != nil {
		return "", 0, err
	}
	return string(decoded), rank, nil
}

func validateContiguousRanks(seen map[int]struct{}, count int) error {
	for i := 0; i < count; i++ {
		if _, ok := seen[i]; !ok {
			return errNonContiguousRanks
		}
	}
	return nil
}
