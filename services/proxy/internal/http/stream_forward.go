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

const (
	streamBackpressureThreshold = 50 * time.Millisecond
	streamDrainTimeout          = 100 * time.Millisecond
)

// errClientWrite tags failures from ResponseWriter.Write (broken pipe, etc.).
var errClientWrite = errors.New("client write failed")

type streamCheckpointResult struct {
	ctx      context.Context
	content  string
	usage    *provider.Usage
	latency  time.Duration
	complete bool
}

type streamForwardParams struct {
	w          http.ResponseWriter
	r          *http.Request
	resp       provider.Response
	provider   string
	metrics    *metrics.ProxyRegistry
	log        *logger.Logger
	docsBase   string
	onComplete func(streamCheckpointResult)
}

// sseCopyDest groups writer-side dependencies for the SSE copy loop.
type sseCopyDest struct {
	w       http.ResponseWriter
	flusher http.Flusher
	src     io.Reader
	metrics *metrics.ProxyRegistry
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
		p.metrics.ObserveStreamDuration(metrics.StreamObservation{
			Provider: p.provider,
			Status:   status,
			Seconds:  time.Since(start).Seconds(),
		})
	}
	content, usage := drainAccumulator(p, acc)
	if p.onComplete != nil {
		p.onComplete(streamCheckpointResult{
			ctx: p.r.Context(), content: content, usage: usage,
			latency: time.Since(start), complete: status == "ok",
		})
	}
}

func writeSSEHeadersAndCopy(p streamForwardParams, flusher http.Flusher, acc *openai.StreamAccumulator) string {
	setSessionResponseHeader(p.w, p.r.Context())
	p.w.Header().Set("Content-Type", "text/event-stream")
	p.w.Header().Set("Cache-Control", "no-cache")
	p.w.Header().Set("X-Accel-Buffering", "no")
	p.w.WriteHeader(http.StatusOK)
	flusher.Flush()

	tee := io.TeeReader(p.resp.Body, acc)
	err := copySSEEvents(p.r.Context(), sseCopyDest{
		w: p.w, flusher: flusher, src: tee, metrics: p.metrics,
	})
	return classifyStreamEnd(p, acc, err)
}

func classifyStreamEnd(p streamForwardParams, acc *openai.StreamAccumulator, err error) string {
	if isClientDisconnect(p.r.Context(), err) {
		noteIncompleteStream(p, streamEndNote{acc: acc, clientSide: true, msg: "client disconnected mid-stream"})
		return "client_disconnect"
	}
	if err != nil {
		noteIncompleteStream(p, streamEndNote{acc: acc, msg: "upstream stream ended with error", err: err})
		return "error"
	}
	if !acc.Complete() {
		noteIncompleteStream(p, streamEndNote{acc: acc, msg: "upstream stream ended without [DONE]"})
		return "incomplete"
	}
	return "ok"
}

func isClientDisconnect(ctx context.Context, err error) bool {
	if errors.Is(err, errClientWrite) {
		return true
	}
	return errors.Is(err, context.Canceled) || errors.Is(ctx.Err(), context.Canceled)
}

type streamEndNote struct {
	acc        *openai.StreamAccumulator
	clientSide bool
	msg        string
	err        error
}

func noteIncompleteStream(p streamForwardParams, n streamEndNote) {
	if p.metrics != nil {
		if n.clientSide {
			p.metrics.IncStreamClientDisconnect()
		} else {
			p.metrics.IncStreamUpstreamDisconnect()
		}
	}
	if n.err != nil {
		p.log.WarnCtx(p.r.Context(), n.msg, "provider", p.provider, "error", n.err.Error())
	} else {
		p.log.WarnCtx(p.r.Context(), n.msg, "provider", p.provider)
	}
	if !n.acc.Complete() {
		n.acc.MarkClosed()
	}
}

func copySSEEvents(ctx context.Context, dest sseCopyDest) error {
	reader := bufio.NewReader(dest.src)
	for {
		if err := ctx.Err(); err != nil {
			return err
		}
		line, readErr := reader.ReadBytes('\n')
		if writeErr := writeLineIfPresent(dest, line); writeErr != nil {
			return writeErr
		}
		if readErr == nil {
			continue
		}
		if errors.Is(readErr, io.EOF) {
			dest.flusher.Flush()
			return nil
		}
		return readErr
	}
}

func writeLineIfPresent(dest sseCopyDest, line []byte) error {
	if len(line) == 0 {
		return nil
	}
	return writeAndMaybeFlush(dest, line)
}

func writeAndMaybeFlush(dest sseCopyDest, line []byte) error {
	start := time.Now()
	if _, err := dest.w.Write(line); err != nil {
		return errors.Join(errClientWrite, err)
	}
	if isSSEEventBoundary(line) {
		dest.flusher.Flush()
	}
	if dest.metrics != nil && time.Since(start) >= streamBackpressureThreshold {
		dest.metrics.IncStreamBackpressure()
	}
	return nil
}

func isSSEEventBoundary(line []byte) bool {
	if len(line) == 1 && line[0] == '\n' {
		return true
	}
	return len(line) == 2 && line[0] == '\r' && line[1] == '\n'
}

func drainAccumulator(p streamForwardParams, acc *openai.StreamAccumulator) (string, *provider.Usage) {
	waitCtx, cancel := context.WithTimeout(p.r.Context(), streamDrainTimeout)
	defer cancel()
	content, usage, err := acc.Wait(waitCtx)
	if err != nil {
		p.log.WarnCtx(p.r.Context(), "stream accumulator drain incomplete",
			"provider", p.provider, "error", err.Error())
		return "", nil
	}
	return content, usage
}
