package provider

import (
	"bytes"
	"context"
	"net/http"
	"strings"
	"time"

	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/trace"
	"go.opentelemetry.io/otel/trace/noop"
)

// HTTPClients holds the sync and streaming upstream clients that share a Transport.
type HTTPClients struct {
	Sync   *http.Client
	Stream *http.Client
}

// NewHTTPClients builds pooled sync + stream clients for a provider adapter.
func NewHTTPClients(timeout time.Duration) HTTPClients {
	syncClient := NewPooledHTTPClient(timeout)
	return HTTPClients{Sync: syncClient, Stream: StreamHTTPClient(syncClient)}
}

// TracerOrNoop returns tracer, or a noop tracer named name when tracer is nil.
func TracerOrNoop(tracer trace.Tracer, name string) trace.Tracer {
	if tracer != nil {
		return tracer
	}
	return noop.NewTracerProvider().Tracer(name)
}

// StartCompleteSpan starts the standard provider Complete span attributes.
func StartCompleteSpan(
	ctx context.Context,
	tracer trace.Tracer,
	spanName, providerName string,
	req Request,
) (context.Context, trace.Span) {
	return tracer.Start(ctx, spanName,
		trace.WithAttributes(
			attribute.String("provider.name", providerName),
			attribute.String("llm.model", req.Model),
			attribute.Bool("llm.stream", req.Stream),
		),
	)
}

// JoinBaseURL joins base and path with a single slash boundary.
func JoinBaseURL(base, path string) string {
	return strings.TrimRight(base, "/") + path
}

// NewJSONPostRequest builds a JSON POST with optional stream Accept header.
func NewJSONPostRequest(ctx context.Context, call UpstreamCall, headers map[string]string) (*http.Request, error) {
	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, call.URL, bytes.NewReader(call.Body))
	if err != nil {
		return nil, err
	}
	for k, v := range headers {
		httpReq.Header.Set(k, v)
	}
	if call.Stream {
		httpReq.Header.Set("Accept", "text/event-stream")
	}
	return httpReq, nil
}

// TimedHTTPOnce is TryHTTPOnce with latency measured for the OK path.
func TimedHTTPOnce(
	maxRetries int,
	attempt int,
	doRequest func() (*http.Response, error),
	incRequest func(statusClass string),
	isRetryableStatus func(int) bool,
	readErr func(*http.Response) *ProviderError,
	onOK func(*http.Response, time.Duration) AttemptOutcome,
) AttemptOutcome {
	start := time.Now()
	return TryHTTPOnce(
		maxRetries,
		attempt,
		doRequest,
		incRequest,
		isRetryableStatus,
		readErr,
		func(resp *http.Response) AttemptOutcome {
			return onOK(resp, time.Since(start))
		},
	)
}
