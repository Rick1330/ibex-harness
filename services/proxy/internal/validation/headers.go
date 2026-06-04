package validation

import (
	"net/http"
	"strings"

	proxyerrors "github.com/Rick1330/ibex-harness/services/proxy/internal/errors"
)

const headerAgentID = "X-IBEX-Agent-ID"

// ValidateChatHeaders validates required IBEX headers for chat completions.
func ValidateChatHeaders(h http.Header) []proxyerrors.FieldError {
	var out []proxyerrors.FieldError
	if fe := ValidateUUIDField("header."+headerAgentID, h.Get(headerAgentID)); fe != nil {
		out = append(out, *fe)
	}
	session := strings.TrimSpace(h.Get("X-IBEX-Session-ID"))
	if session != "" {
		if fe := ValidateUUIDField("header.X-IBEX-Session-ID", session); fe != nil {
			out = append(out, *fe)
		}
	}
	return out
}
