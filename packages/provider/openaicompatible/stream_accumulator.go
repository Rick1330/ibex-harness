package openaicompatible

import (
	"bytes"
	"context"
	"encoding/json"
	"strings"
	"sync"
	"unicode/utf8"

	"github.com/Rick1330/ibex-harness/packages/provider"
)

// MaxAccumulatedContentBytes is the soft cap for accumulated completion text (ADR-0027).
const MaxAccumulatedContentBytes = 1 << 20 // 1 MiB

const doneSentinel = "[DONE]"

// StreamAccumulator collects completion text and usage from an OpenAI SSE body.
// Write is best-effort: parse failures never fail the forward path (ADR-0027).
type StreamAccumulator struct {
	mu        sync.Mutex
	buf       bytes.Buffer
	content   strings.Builder
	usage     *provider.Usage
	done      chan struct{}
	complete  bool
	closed    bool
	capped    bool
	closeOnce sync.Once
}

// NewStreamAccumulator constructs an empty accumulator.
func NewStreamAccumulator() *StreamAccumulator {
	return &StreamAccumulator{done: make(chan struct{})}
}

// Write implements io.Writer. It always returns len(p), nil.
func (a *StreamAccumulator) Write(p []byte) (int, error) {
	a.mu.Lock()
	if a.closed {
		a.mu.Unlock()
		return len(p), nil
	}
	_, _ = a.buf.Write(p)
	a.drainLocked()
	sawDone := a.complete
	a.mu.Unlock()
	if sawDone {
		a.signalDone()
	}
	return len(p), nil
}

// Wait blocks until [DONE] is observed or ctx is cancelled.
func (a *StreamAccumulator) Wait(ctx context.Context) (string, *provider.Usage, error) {
	select {
	case <-a.done:
		a.mu.Lock()
		defer a.mu.Unlock()
		return a.content.String(), a.usage, nil
	case <-ctx.Done():
		return "", nil, ctx.Err()
	}
}

// Complete reports whether the OpenAI [DONE] sentinel was seen.
func (a *StreamAccumulator) Complete() bool {
	a.mu.Lock()
	defer a.mu.Unlock()
	return a.complete
}

// MarkClosed signals end-of-stream without [DONE] (upstream EOF / error).
func (a *StreamAccumulator) MarkClosed() {
	a.mu.Lock()
	a.closed = true
	a.mu.Unlock()
	a.signalDone()
}

func (a *StreamAccumulator) signalDone() {
	a.closeOnce.Do(func() { close(a.done) })
}

func (a *StreamAccumulator) drainLocked() {
	for {
		line, ok := a.readLineLocked()
		if !ok {
			return
		}
		a.handleLineLocked(line)
	}
}

func (a *StreamAccumulator) readLineLocked() (string, bool) {
	data := a.buf.Bytes()
	idx := bytes.IndexByte(data, '\n')
	if idx < 0 {
		return "", false
	}
	line := string(data[:idx])
	a.buf.Next(idx + 1)
	return strings.TrimRight(line, "\r"), true
}

func (a *StreamAccumulator) handleLineLocked(line string) {
	if !strings.HasPrefix(line, "data:") {
		return
	}
	payload := strings.TrimSpace(strings.TrimPrefix(line, "data:"))
	if payload == doneSentinel {
		a.complete = true
		a.closed = true
		return
	}
	a.parseChunkLocked(payload)
}

func (a *StreamAccumulator) parseChunkLocked(payload string) {
	var chunk streamChunk
	if err := json.Unmarshal([]byte(payload), &chunk); err != nil {
		return
	}
	if chunk.Usage != nil {
		a.usage = &provider.Usage{
			InputTokens:  chunk.Usage.PromptTokens,
			OutputTokens: chunk.Usage.CompletionTokens,
			TotalTokens:  chunk.Usage.TotalTokens,
		}
	}
	for _, ch := range chunk.Choices {
		a.appendContentLocked(ch.Delta.Content)
	}
}

func (a *StreamAccumulator) appendContentLocked(s string) {
	if s == "" || a.capped {
		return
	}
	remaining := MaxAccumulatedContentBytes - a.content.Len()
	if remaining <= 0 {
		a.capped = true
		return
	}
	if len(s) <= remaining {
		a.content.WriteString(s)
		return
	}
	trunc := s[:remaining]
	for len(trunc) > 0 && !utf8.ValidString(trunc) {
		trunc = trunc[:len(trunc)-1]
	}
	if len(trunc) > 0 {
		a.content.WriteString(trunc)
	}
	a.capped = true
}

type streamChunk struct {
	Choices []struct {
		Delta struct {
			Content string `json:"content"`
		} `json:"delta"`
	} `json:"choices"`
	Usage *struct {
		PromptTokens     int `json:"prompt_tokens"`
		CompletionTokens int `json:"completion_tokens"`
		TotalTokens      int `json:"total_tokens"`
	} `json:"usage"`
}
