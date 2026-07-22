package http

import (
	"net/http"

	"github.com/Rick1330/ibex-harness/services/proxy/internal/llm"
)

type chatParseOpts struct {
	docsBase string
}

// ChatParseMiddleware parses and validates the chat completion body once, then
// attaches llm.ChatCompletionRequest so downstream middleware and handlers
// consume the typed request without re-parsing the body.
func ChatParseMiddleware(opts chatParseOpts) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if !requireMethod(w, r, http.MethodPost, opts.docsBase) {
				return
			}
			requestID := requestIDFromContext(r.Context())
			parsed, ok := parseAndValidateChatRequest(w, r, requestID, opts.docsBase)
			if !ok {
				return
			}
			ctx := llm.WithChatRequest(r.Context(), parsed)
			next.ServeHTTP(w, r.WithContext(ctx))
		})
	}
}
