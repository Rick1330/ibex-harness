package main

import (
	"flag"
	"fmt"
	"io"
)

func parseExportArgs(args []string, stderr io.Writer) (outPath, checkPath string, code int) {
	fs := flag.NewFlagSet("export_capabilities", flag.ContinueOnError)
	fs.SetOutput(stderr)
	out := fs.String("o", "", "write JSON to this path (default: stdout)")
	check := fs.String("check", "", "exit 1 if committed JSON at path differs from freshly generated export")
	if err := fs.Parse(args); err != nil {
		return "", "", 2
	}
	if *out != "" && *check != "" {
		_, _ = fmt.Fprintln(stderr, "export_capabilities: use -o or -check, not both")
		return "", "", 2
	}
	return *out, *check, 0
}
