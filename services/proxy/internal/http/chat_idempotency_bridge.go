package http

import (
	"net/http"
	"time"

	"github.com/Rick1330/ibex-harness/packages/idempotency"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/http/chat"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/llm"
)

type idempotencyClaim = chat.Claim
type capturingWriter = chat.CapturingWriter

func (h chatCompletionHandler) idemp() chat.Idempotency {
	return chat.Idempotency{
		Store:         h.idempotencyStore,
		Metrics:       h.metrics,
		Log:           h.log,
		DocsBase:      h.docsBase,
		Timeout:       h.idempotencyTimeout,
		CommitTimeout: h.idempotencyCommitTimeout,
	}
}

func (h chatCompletionHandler) resolveIdempotency(
	w http.ResponseWriter,
	r *http.Request,
	parsed *llm.ChatCompletionRequest,
) (*idempotencyClaim, bool) {
	return h.idemp().Resolve(w, r, parsed)
}

func replayIdempotency(w http.ResponseWriter, rec idempotency.Record) {
	chat.Replay(w, rec)
}

func idempotencyCASHTimeout(claimBudget time.Duration) time.Duration {
	return chat.CASTimeout(claimBudget)
}

func (h chatCompletionHandler) finishIdempotency(claim *idempotencyClaim, status int, body []byte) {
	h.idemp().Finish(claim, status, body)
}
