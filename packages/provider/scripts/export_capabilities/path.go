package main

import (
	"fmt"
	"path/filepath"
)

// resolveCatalogPath requires the leaf name model_capabilities.v1.json and returns
// an absolute cleaned path so CLI -o/-check cannot be used as an open-ended file API.
func resolveCatalogPath(path string) (string, error) {
	trimmed := filepath.Clean(path)
	if trimmed == "." || trimmed == "" {
		return "", fmt.Errorf("empty path")
	}
	if filepath.Base(trimmed) != catalogFileName {
		return "", fmt.Errorf("path must end with %s", catalogFileName)
	}
	abs, err := filepathAbs(trimmed)
	if err != nil {
		return "", err
	}
	if filepath.Base(abs) != catalogFileName {
		return "", fmt.Errorf("path must end with %s", catalogFileName)
	}
	return abs, nil
}
