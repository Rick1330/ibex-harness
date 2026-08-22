package tokenizer

import (
	"fmt"
	"os"
	"path"
	"path/filepath"
	"strings"
)

type assetDirPath string

type assetBasename string

type jailedAssetRef struct {
	root     assetDirPath
	basename assetBasename
}

func (r jailedAssetRef) filesystemPath() string {
	return filepath.Join(string(r.root), string(r.basename))
}

func jailedAssetPath(assetDir assetDirPath, base assetBasename) (string, error) {
	ref, err := jailedAssetLocation(assetDir, base)
	if err != nil {
		return "", err
	}
	return ref.filesystemPath(), nil
}

func jailedAssetLocation(assetDir assetDirPath, base assetBasename) (jailedAssetRef, error) {
	safeBase, err := sanitizeAssetBasename(base)
	if err != nil {
		return jailedAssetRef{}, err
	}
	root, err := filepath.Abs(filepath.Clean(string(assetDir)))
	if err != nil {
		return jailedAssetRef{}, err
	}
	ref := jailedAssetRef{root: assetDirPath(root), basename: safeBase}
	if err := assertPathUnderRoot(ref); err != nil {
		return jailedAssetRef{}, err
	}
	return ref, nil
}

func assertPathUnderRoot(ref jailedAssetRef) error {
	resolved := ref.filesystemPath()
	rel, err := filepath.Rel(string(ref.root), resolved)
	if err != nil || strings.HasPrefix(rel, "..") {
		return fmt.Errorf("%w: %q", ErrAssetPathEscape, ref.basename)
	}
	return nil
}

func sanitizeAssetBasename(base assetBasename) (assetBasename, error) {
	trimmed := strings.TrimSpace(string(base))
	if trimmed == "" {
		return "", fmt.Errorf("%w: invalid asset basename %q", ErrAssetPathEscape, base)
	}
	if trimmed != path.Base(trimmed) {
		return "", fmt.Errorf("%w: invalid asset basename %q", ErrAssetPathEscape, base)
	}
	if strings.Contains(trimmed, string(os.PathSeparator)) {
		return "", fmt.Errorf("%w: invalid asset basename %q", ErrAssetPathEscape, base)
	}
	return assetBasename(trimmed), nil
}
