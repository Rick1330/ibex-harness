package main

import (
	"bytes"
	"fmt"
	"io"
	"path/filepath"
)

func checkFresh(committedPath string, fresh []byte, stderr io.Writer) int {
	resolved, err := resolveCatalogPath(committedPath)
	if err != nil {
		_, _ = fmt.Fprintf(stderr, "export_capabilities: path: %v\n", err)
		return 2
	}
	committed, err := osReadFile(resolved) // #nosec G304 -- path constrained by resolveCatalogPath
	if err != nil {
		_, _ = fmt.Fprintf(stderr, "export_capabilities: read %s: %v\n", resolved, err)
		return 2
	}
	if bytes.Equal(normalizeNewline(committed), normalizeNewline(fresh)) {
		_, _ = fmt.Fprintf(stderr, "OK: %s matches BuiltInCapabilityCatalog export\n", filepath.Base(resolved))
		return 0
	}
	_, _ = fmt.Fprintf(
		stderr,
		"export_capabilities: %s is stale — run:\n  go run ./packages/provider/scripts/export_capabilities -o %s\n",
		resolved,
		resolved,
	)
	return 1
}
