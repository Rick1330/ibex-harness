package http

import (
	"context"
	"net/http"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/llm"
)

type chatParseOpts struct {
	log      *logger.Logger
	docsBase string
}

// ChatParseMiddleware parses and validates the chat completion body, then
// attaches llm.ChatCompletionRequest to the request context for downstream middleware.
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
			logChatParsed(opts.log, ctx, parsed)
			next.ServeHTTP(w, r.WithContext(ctx))
		})
	}
}

func logChatParsed(log *logger.Logger, ctx context.Context, parsed *llm.ChatCompletionRequest) {
	if log == nil || parsed == nil {
		return
	}
	res, ok := auth.FromContext(ctx)
	if !ok {
		return
	}
	log.InfoCtx(ctx, "chat completion parsed",
		"org_id", res.OrgID,
		"model", parsed.Model,
		"message_count", len(parsed.Messages),
		"stream", parsed.Stream,
	)
}
