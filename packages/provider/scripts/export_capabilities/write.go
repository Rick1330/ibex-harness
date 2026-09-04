package main

import (
	"fmt"
	"io"
	"os"
	"path/filepath"
)

// tempFile is the subset of *os.File used by writeAtomic (injectable in tests).
type tempFile interface {
	Name() string
	Write([]byte) (int, error)
	Close() error
}

// OS seams — swapped in tests to exercise failure paths without brittle filesystem races.
var (
	osReadFile   = os.ReadFile
	osCreateTemp = func(dir, pattern string) (tempFile, error) { return os.CreateTemp(dir, pattern) }
	osRename     = os.Rename
	osChmod      = os.Chmod
	osRemove     = os.Remove
	filepathAbs  = filepath.Abs
)

func writeExportFile(path string, raw []byte, modelCount int, stderr io.Writer) int {
	resolved, err := resolveCatalogPath(path)
	if err != nil {
		_, _ = fmt.Fprintf(stderr, "export_capabilities: path: %v\n", err)
		return 2
	}
	if err := writeAtomic(resolved, raw, 0o644); err != nil {
		_, _ = fmt.Fprintf(stderr, "export_capabilities: write %s: %v\n", resolved, err)
		return 2
	}
	_, _ = fmt.Fprintf(stderr, "wrote %s (%d models)\n", resolved, modelCount)
	return 0
}

func writeExportStdout(stdout, stderr io.Writer, raw []byte) int {
	n, err := stdout.Write(raw)
	if err != nil {
		_, _ = fmt.Fprintf(stderr, "export_capabilities: stdout write: %v\n", err)
		return 2
	}
	if n != len(raw) {
		_, _ = fmt.Fprintf(stderr, "export_capabilities: short stdout write: %d/%d\n", n, len(raw))
		return 2
	}
	return 0
}

func writeAtomic(path string, data []byte, perm os.FileMode) error {
	dir := filepath.Dir(path)
	tmp, err := osCreateTemp(dir, ".model_capabilities.*.tmp")
	if err != nil {
		return err
	}
	tmpName := tmp.Name()
	cleanup := true
	defer func() {
		if cleanup {
			_ = osRemove(tmpName)
		}
	}()
	if _, err := tmp.Write(data); err != nil {
		_ = tmp.Close()
		return err
	}
	if err := tmp.Close(); err != nil {
		return err
	}
	if err := osChmod(tmpName, perm); err != nil {
		return err
	}
	if err := osRename(tmpName, path); err != nil {
		return err
	}
	cleanup = false
	return nil
}
