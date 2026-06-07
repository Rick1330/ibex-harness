package validation

import (
	"net/http"
	"strings"

	proxyerrors "github.com/Rick1330/ibex-harness/services/proxy/internal/errors"
)

// HeaderAgentID is the required agent identity header on protected proxy routes.
const HeaderAgentID = "X-IBEX-Agent-ID"

// ValidateChatHeaders validates optional IBEX session header for chat completions.
// Agent ID is verified by AgentVerificationMiddleware before the handler runs.
func ValidateChatHeaders(h http.Header) []proxyerrors.FieldError {
	var out []proxyerrors.FieldError
	session := strings.TrimSpace(h.Get("X-IBEX-Session-ID"))
	if session != "" {
		if fe := ValidateUUIDField("header.X-IBEX-Session-ID", session); fe != nil {
			out = append(out, *fe)
		}
	}
	return out
}
