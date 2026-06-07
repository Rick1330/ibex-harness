// Package logger provides a structured JSON logger for IBEX Harness Go services.
package logger

import (
	"context"
	"errors"
	"io"
	"log/slog"
	"os"
)

// Logger is the IBEX Harness structured logger. Construct with New().
type Logger struct {
	inner   *slog.Logger
	service string
}

// Config configures the logger at startup.
type Config struct {
	Service   string
	Level     slog.Level
	AddSource bool
	Writer    io.Writer
}

// New constructs a Logger writing JSON to stderr (or cfg.Writer when set).
func New(cfg Config) (*Logger, error) {
	if cfg.Service == "" {
		return nil, errors.New("logger: Service is required")
	}
	if cfg.Level == 0 {
		cfg.Level = slog.LevelInfo
	}
	w := cfg.Writer
	if w == nil {
		w = os.Stderr
	}
	h := newIBEXHandler(cfg.Service, cfg.Level, w, cfg.AddSource)
	return &Logger{inner: slog.New(h), service: cfg.Service}, nil
}

// With returns a Logger with attributes pre-attached to every subsequent line.
func (l *Logger) With(args ...any) *Logger {
	return &Logger{inner: l.inner.With(args...), service: l.service}
}

func (l *Logger) logCtx(ctx context.Context, level slog.Level, msg string, args ...any) {
	l.inner.Log(ctx, level, msg, args...)
}

// DebugCtx emits a DEBUG log line.
func (l *Logger) DebugCtx(ctx context.Context, msg string, args ...any) {
	l.logCtx(ctx, slog.LevelDebug, msg, args...)
}

// InfoCtx emits an INFO log line.
func (l *Logger) InfoCtx(ctx context.Context, msg string, args ...any) {
	l.logCtx(ctx, slog.LevelInfo, msg, args...)
}

// WarnCtx emits a WARN log line.
func (l *Logger) WarnCtx(ctx context.Context, msg string, args ...any) {
	l.logCtx(ctx, slog.LevelWarn, msg, args...)
}

// ErrorCtx emits an ERROR log line.
func (l *Logger) ErrorCtx(ctx context.Context, msg string, args ...any) {
	l.logCtx(ctx, slog.LevelError, msg, args...)
}
