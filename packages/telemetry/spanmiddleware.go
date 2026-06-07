package telemetry

import (
	"net/http"

	"go.opentelemetry.io/otel"
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
			ctx, span := startRequestSpan(ctx, tracer, r)

			rec := &spanStatusRecorder{ResponseWriter: w, status: http.StatusOK}
			next.ServeHTTP(rec, r.WithContext(ctx))
			finishRequestSpan(span, rec.status)
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
