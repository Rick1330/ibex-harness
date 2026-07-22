package http

import (
	"bufio"
	"context"
	"errors"
	"io"
	"net/http"
	"time"

	apierror "github.com/Rick1330/ibex-harness/packages/apierror"
	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/packages/provider/openai"
)

const streamBackpressureThreshold = 50 * time.Millisecond

type streamForwardParams struct {
	w        http.ResponseWriter
	r        *http.Request
	resp     provider.Response
	provider string
	metrics  *metrics.ProxyRegistry
	log      *logger.Logger
	docsBase string
}

func forwardSSEStream(p streamForwardParams) {
	flusher, ok := p.w.(http.Flusher)
	if !ok {
		requestID := requestIDFromContext(p.r.Context())
		p.log.ErrorCtx(p.r.Context(), "ResponseWriter does not support http.Flusher; streaming not possible")
		apierror.WriteStatus(p.w, http.StatusInternalServerError, apierror.CodeInternalError,
			"Streaming not supported by server", requestID,
			apierror.WriteOpts{DocsBase: p.docsBase})
		return
	}

	acc := openai.NewStreamAccumulator()
	start := time.Now()
	status := writeSSEHeadersAndCopy(p, flusher, acc)
	if p.metrics != nil {
		p.metrics.ObserveStreamDuration(p.provider, status, time.Since(start).Seconds())
	}
	_, _ = drainAccumulator(p.r.Context(), acc)
}

func writeSSEHeadersAndCopy(p streamForwardParams, flusher http.Flusher, acc *openai.StreamAccumulator) string {
	p.w.Header().Set("Content-Type", "text/event-stream")
	p.w.Header().Set("Cache-Control", "no-cache")
	p.w.Header().Set("X-Accel-Buffering", "no")
	p.w.WriteHeader(http.StatusOK)
	flusher.Flush()

	tee := io.TeeReader(p.resp.Body, acc)
	err := copySSEEvents(p.r.Context(), p.w, flusher, tee, p.metrics)
	if errors.Is(err, context.Canceled) || errors.Is(p.r.Context().Err(), context.Canceled) {
		if p.metrics != nil {
			p.metrics.IncStreamClientDisconnect()
		}
		p.log.WarnCtx(p.r.Context(), "client disconnected mid-stream", "provider", p.provider)
		if !acc.Complete() {
			acc.MarkClosed()
		}
		return "client_disconnect"
	}
	if err != nil {
		if p.metrics != nil {
			p.metrics.IncStreamUpstreamDisconnect()
		}
		p.log.WarnCtx(p.r.Context(), "upstream stream ended with error", "provider", p.provider, "error", err.Error())
		if !acc.Complete() {
			acc.MarkClosed()
		}
		return "error"
	}
	if !acc.Complete() {
		if p.metrics != nil {
			p.metrics.IncStreamUpstreamDisconnect()
		}
		p.log.WarnCtx(p.r.Context(), "upstream stream ended without [DONE]", "provider", p.provider)
		acc.MarkClosed()
		return "incomplete"
	}
	return "ok"
}

func copySSEEvents(ctx context.Context, w http.ResponseWriter, flusher http.Flusher, src io.Reader, reg *metrics.ProxyRegistry) error {
	reader := bufio.NewReader(src)
	for {
		if err := ctx.Err(); err != nil {
			return err
		}
		line, err := reader.ReadBytes('\n')
		if len(line) > 0 {
			if writeErr := writeAndMaybeFlush(w, flusher, line, reg); writeErr != nil {
				return writeErr
			}
		}
		if err != nil {
			if errors.Is(err, io.EOF) {
				return nil
			}
			return err
		}
	}
}

func writeAndMaybeFlush(w http.ResponseWriter, flusher http.Flusher, line []byte, reg *metrics.ProxyRegistry) error {
	start := time.Now()
	_, err := w.Write(line)
	if err != nil {
		return err
	}
	// Blank line (SSE event boundary): "\n" alone or "\r\n" after prior content ends event.
	if isSSEEventBoundary(line) {
		flusher.Flush()
	}
	if reg != nil && time.Since(start) >= streamBackpressureThreshold {
		reg.IncStreamBackpressure()
	}
	return nil
}

func isSSEEventBoundary(line []byte) bool {
	return len(line) == 1 && line[0] == '\n' ||
		len(line) == 2 && line[0] == '\r' && line[1] == '\n'
}

func drainAccumulator(ctx context.Context, acc *openai.StreamAccumulator) (string, *provider.Usage) {
	waitCtx, cancel := context.WithTimeout(ctx, 100*time.Millisecond)
	defer cancel()
	content, usage, err := acc.Wait(waitCtx)
	if err != nil {
		return "", nil
	}
	return content, usage
}
