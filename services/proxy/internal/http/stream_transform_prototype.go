// Package http — stream_transform_prototype.go
//
// THROWAWAY / DESIGN SPIKE ONLY (milestone 2.5.G3.M2 / ADR-0045).
// This file is intentionally NOT wired into forwardSSEStream, copySSEEvents,
// bootstrap, or any production request path. It validates token-window buffering
// latency and fail-closed overflow behavior before Phase 3 commits to a design.
package http

import (
	"errors"
	"regexp"
	"strings"
	"unicode/utf8"
)

// Prototype defaults for design validation (not production PII packs).
const (
	prototypeDefaultHoldbackRunes  = 64
	prototypeDefaultMaxBufferRunes = 4096
	prototypeRedactToken           = "[REDACTED]"
	// prototypeMaxPatternRunes is len("SECRET")+8 digits; holdback must be >= this
	// or a complete match near the cut line can leak a prefix before redaction.
	prototypeMaxPatternRunes = 14
	// prototypeAbsoluteMaxBufferRunes is a hard ceiling on HoldbackRunes and
	// MaxBufferRunes to bound DoS from misconfiguration (1 MiB of runes).
	prototypeAbsoluteMaxBufferRunes = 1 << 20
)

// ErrPrototypeBufferOverflow is returned when the window would exceed MaxBufferRunes.
// Callers that eventually wire this must abort the stream (fail-closed), never leak.
var ErrPrototypeBufferOverflow = errors.New("stream transform prototype: buffer overflow")

// ErrPrototypeInvalidConfig is returned for non-positive holdback/max or holdback > max.
var ErrPrototypeInvalidConfig = errors.New("stream transform prototype: invalid config")

// prototypeSecretPattern matches a synthetic secret token for design tests only.
// Max match length is 14 runes ("SECRET" + up to 8 digits); holdback must be >= that.
var prototypeSecretPattern = regexp.MustCompile(`SECRET[0-9]{1,8}`)

// PrototypeWindowConfig configures the throwaway holdback buffer.
type PrototypeWindowConfig struct {
	HoldbackRunes  int
	MaxBufferRunes int
}

// PrototypeWindowBuffer holds a trailing rune window so pattern matches that
// straddle chunk boundaries are not emitted until complete (or stream end).
// Not goroutine-safe; one buffer per stream.
type PrototypeWindowBuffer struct {
	holdback int
	maxBuf   int
	buf      strings.Builder
}

// NewPrototypeWindowBuffer constructs a buffer. Zero values use prototype defaults.
func NewPrototypeWindowBuffer(cfg PrototypeWindowConfig) (*PrototypeWindowBuffer, error) {
	holdback, maxBuf := normalizePrototypeConfig(cfg)
	if err := validatePrototypeConfig(holdback, maxBuf); err != nil {
		return nil, err
	}
	return &PrototypeWindowBuffer{holdback: holdback, maxBuf: maxBuf}, nil
}

func normalizePrototypeConfig(cfg PrototypeWindowConfig) (holdback, maxBuf int) {
	holdback = cfg.HoldbackRunes
	if holdback == 0 {
		holdback = prototypeDefaultHoldbackRunes
	}
	maxBuf = cfg.MaxBufferRunes
	if maxBuf == 0 {
		maxBuf = prototypeDefaultMaxBufferRunes
	}
	return holdback, maxBuf
}

func validatePrototypeConfig(holdback, maxBuf int) error {
	if holdback < prototypeMaxPatternRunes {
		return ErrPrototypeInvalidConfig
	}
	if maxBuf < 1 {
		return ErrPrototypeInvalidConfig
	}
	if holdback > maxBuf {
		return ErrPrototypeInvalidConfig
	}
	if holdback > prototypeAbsoluteMaxBufferRunes || maxBuf > prototypeAbsoluteMaxBufferRunes {
		return ErrPrototypeInvalidConfig
	}
	return nil
}

// Feed appends a content chunk, redacts complete prototype matches, and returns
// only the prefix that is safe to flush (retaining a holdback tail).
func (w *PrototypeWindowBuffer) Feed(chunk string) (string, error) {
	if w == nil {
		return "", ErrPrototypeInvalidConfig
	}
	if chunk == "" {
		return "", nil
	}
	if w.wouldOverflow(chunk) {
		return "", ErrPrototypeBufferOverflow
	}
	w.buf.WriteString(chunk)
	return w.emitSafe(false)
}

func (w *PrototypeWindowBuffer) wouldOverflow(chunk string) bool {
	return utf8.RuneCountInString(w.buf.String())+utf8.RuneCountInString(chunk) > w.maxBuf
}

// Flush redacts any remaining complete matches and emits the entire buffer
// (stream end — no further chunks can complete a partial match).
func (w *PrototypeWindowBuffer) Flush() (string, error) {
	if w == nil {
		return "", ErrPrototypeInvalidConfig
	}
	return w.emitSafe(true)
}

// RetainedRunes reports runes currently held (for benchmarks / metrics sketches).
func (w *PrototypeWindowBuffer) RetainedRunes() int {
	if w == nil {
		return 0
	}
	return utf8.RuneCountInString(w.buf.String())
}

func (w *PrototypeWindowBuffer) emitSafe(flushAll bool) (string, error) {
	redacted := w.redactAndStore()
	if flushAll {
		w.buf.Reset()
		return redacted, nil
	}
	return w.emitHoldbackPrefix(redacted)
}

func (w *PrototypeWindowBuffer) redactAndStore() string {
	redacted := prototypeSecretPattern.ReplaceAllString(w.buf.String(), prototypeRedactToken)
	w.buf.Reset()
	w.buf.WriteString(redacted)
	return redacted
}

func (w *PrototypeWindowBuffer) emitHoldbackPrefix(redacted string) (string, error) {
	runes := []rune(redacted)
	if len(runes) <= w.holdback {
		return "", nil
	}
	cut := len(runes) - w.holdback
	emit := string(runes[:cut])
	w.buf.Reset()
	w.buf.WriteString(string(runes[cut:]))
	return emit, nil
}
