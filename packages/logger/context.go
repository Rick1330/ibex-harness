package logger

import (
	"context"

	"github.com/Rick1330/ibex-harness/packages/reqid"
	"go.opentelemetry.io/otel/trace"
)

func requestIDFrom(ctx context.Context) string {
	id, ok := reqid.FromContext(ctx)
	if !ok {
		return ""
	}
	return id
}

func traceIDFrom(ctx context.Context) string {
	span := trace.SpanFromContext(ctx)
	if !span.SpanContext().IsValid() {
		return ""
	}
	return span.SpanContext().TraceID().String()
}
