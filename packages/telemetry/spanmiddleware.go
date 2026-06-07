package telemetry

import (
	"net/http"
	"strconv"

	"github.com/Rick1330/ibex-harness/packages/reqid"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/propagation"
	"go.opentelemetry.io/otel/trace"
)

// SpanMiddleware creates a server-side OTel span for every HTTP request.
// Span name format: "{method} {route_template}".
func SpanMiddleware(tracer trace.Tracer) func(http.Handler) http.Handler {
	if tracer == nil {
		return func(next http.Handler) http.Handler { return next }
	}
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			ctx := otel.GetTextMapPropagator().Extract(r.Context(), propagation.HeaderCarrier(r.Header))
			route := r.Pattern
			if route == "" {
				route = "/unknown"
			}
			spanName := r.Method + " " + route

			var contentLen int64
			if r.ContentLength > 0 {
				contentLen = r.ContentLength
			}

			ctx, span := tracer.Start(ctx, spanName, trace.WithSpanKind(trace.SpanKindServer))
			defer span.End()

			span.SetAttributes(
				attribute.String("http.method", r.Method),
				attribute.String("http.route", route),
				attribute.Int64("http.request_content_length", contentLen),
			)
			if id, ok := reqid.FromContext(ctx); ok {
				span.SetAttributes(attribute.String("ibex.request_id", id))
			}

			rec := &spanStatusRecorder{ResponseWriter: w, status: http.StatusOK}
			next.ServeHTTP(rec, r.WithContext(ctx))

			span.SetAttributes(attribute.Int("http.status_code", rec.status))
			if rec.status >= http.StatusInternalServerError {
				span.SetStatus(codes.Error, "HTTP "+strconv.Itoa(rec.status))
			}
		})
	}
}

type spanStatusRecorder struct {
	http.ResponseWriter
	status int
}

func (r *spanStatusRecorder) WriteHeader(status int) {
	r.status = status
	r.ResponseWriter.WriteHeader(status)
}
