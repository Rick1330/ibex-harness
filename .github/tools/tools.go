//go:build tools

// Hash-locked Go CI tools (Sonar: predictable dependency versions via go.sum).
package tools

import (
	_ "golang.org/x/vuln/cmd/govulncheck"
	_ "gotest.tools/gotestsum"
)
