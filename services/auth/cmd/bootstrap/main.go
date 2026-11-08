// Command bootstrap creates the first v1-single-node identity.
//
// The implementation lives in services/auth/internal/bootstrap so the command
// stays an entrypoint only (AGENTS.md §7.1).
package main

import (
	"os"

	"github.com/Rick1330/ibex-harness/services/auth/internal/bootstrap"
)

func main() {
	os.Exit(bootstrap.Run(os.Stdout, os.Stderr, os.Getenv))
}
