package logger

import (
	"context"
	"io"
	"log/slog"
	"strings"
	"time"
)

type ibexHandler struct {
	service string
	inner   slog.Handler
}

func newIBEXHandler(service string, level slog.Level, w io.Writer, addSource bool) *ibexHandler {
	inner := slog.NewJSONHandler(w, &slog.HandlerOptions{
		Level:       level,
		AddSource:   addSource,
		ReplaceAttr: replaceAttr,
	})
	return &ibexHandler{service: service, inner: inner}
}

func replaceAttr(_ []string, a slog.Attr) slog.Attr {
	switch a.Key {
	case slog.TimeKey:
		return slog.String("timestamp", a.Value.Time().Format(time.RFC3339Nano))
	case slog.LevelKey:
		return slog.String("level", strings.ToUpper(a.Value.String()))
	case slog.MessageKey:
		return slog.String("message", a.Value.String())
	default:
		return redactAttr(a)
	}
}

func (h *ibexHandler) Enabled(ctx context.Context, level slog.Level) bool {
	return h.inner.Enabled(ctx, level)
}

func (h *ibexHandler) Handle(ctx context.Context, r slog.Record) error {
	r.AddAttrs(
		slog.String("service", h.service),
		slog.String("request_id", requestIDFrom(ctx)),
		slog.String("trace_id", traceIDFrom(ctx)),
	)
	return h.inner.Handle(ctx, r)
}

func (h *ibexHandler) WithAttrs(attrs []slog.Attr) slog.Handler {
	return &ibexHandler{service: h.service, inner: h.inner.WithAttrs(attrs)}
}

func (h *ibexHandler) WithGroup(name string) slog.Handler {
	return &ibexHandler{service: h.service, inner: h.inner.WithGroup(name)}
}
