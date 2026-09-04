// Command export_capabilities serializes BuiltInCapabilityCatalog (+ tokenizer
// family estimate policy) to the committed generate-and-diff JSON artifact used
// by services/context (ADR-0067 / milestone 3.5.C.1).
package main

import (
	"fmt"
	"io"
	"os"

	"github.com/Rick1330/ibex-harness/packages/provider"
)

// exitFunc is swapped in tests so main can be exercised without os.Exit.
var exitFunc = os.Exit

func main() {
	exitFunc(run(os.Args[1:], os.Stdout, os.Stderr))
}

func run(args []string, stdout, stderr io.Writer) int {
	outPath, checkPath, code := parseExportArgs(args, stderr)
	if code != 0 {
		return code
	}

	doc := buildExport(provider.BuiltInCapabilityCatalog())
	raw, err := marshalCanonical(doc)
	if err != nil {
		_, _ = fmt.Fprintf(stderr, "export_capabilities: marshal: %v\n", err)
		return 2
	}

	switch {
	case checkPath != "":
		return checkFresh(checkPath, raw, stderr)
	case outPath != "":
		return writeExportFile(outPath, raw, len(doc.Models), stderr)
	default:
		return writeExportStdout(stdout, stderr, raw)
	}
}
