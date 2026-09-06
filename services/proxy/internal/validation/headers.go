package validation

import (
	"net/http"
	"strings"

	apierror "github.com/Rick1330/ibex-harness/packages/apierror"
)

// HeaderAgentID is the required agent identity header on protected proxy routes.
const HeaderAgentID = "X-IBEX-Agent-ID"

// HeaderSkipMemory opts out of context-assembly gRPC (3.5.D.2); Phase 2 directive
// injection still applies. Truthy values: 1, true, yes, on (case-insensitive).
const HeaderSkipMemory = "X-IBEX-Skip-Memory"

// ValidateChatHeaders validates optional IBEX session header for chat completions.
// Agent ID is verified by AgentVerificationMiddleware before the handler runs.
func ValidateChatHeaders(h http.Header) []apierror.FieldError {
	var out []apierror.FieldError
	session := strings.TrimSpace(h.Get("X-IBEX-Session-ID"))
	if session != "" {
		if fe := ValidateUUIDField("header.X-IBEX-Session-ID", session); fe != nil {
			out = append(out, *fe)
		}
	}
	return out
}
