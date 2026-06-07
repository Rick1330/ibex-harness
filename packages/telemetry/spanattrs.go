package telemetry

import (
	"context"
	"net/http"

	"github.com/Rick1330/ibex-harness/packages/reqid"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/trace"
)

func spanRoute(r *http.Request) string {
	if r.Pattern != "" {
		return r.Pattern
	}
	return "/unknown"
}

func startRequestSpan(ctx context.Context, tracer trace.Tracer, r *http.Request) (context.Context, trace.Span) {
	route := spanRoute(r)
	spanName := r.Method + " " + route
	ctx, span := tracer.Start(ctx, spanName, trace.WithSpanKind(trace.SpanKindServer))

	var contentLen int64
	if r.ContentLength > 0 {
		contentLen = r.ContentLength
	}
	attrs := []attribute.KeyValue{
		attribute.String("http.method", r.Method),
		attribute.String("http.route", route),
		attribute.Int64("http.request_content_length", contentLen),
	}
	if id, ok := reqid.FromContext(ctx); ok {
		attrs = append(attrs, attribute.String("ibex.request_id", id))
	}
	span.SetAttributes(attrs...)
	return ctx, span
}

func finishRequestSpan(span trace.Span, status int) {
	span.SetAttributes(attribute.Int("http.status_code", status))
	if status >= http.StatusInternalServerError {
		span.SetStatus(codes.Error, http.StatusText(status))
	}
	span.End()
}
