package telemetry

import (
	"context"

	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	"go.opentelemetry.io/otel/trace"
)

// NoopTracer returns a tracer that creates valid span contexts without exporting.
func NoopTracer(instrumentationName string) trace.Tracer {
	tp := sdktrace.NewTracerProvider(sdktrace.WithSampler(sdktrace.AlwaysSample()))
	return tp.Tracer(instrumentationName)
}

// InitForTest initialises providers with an in-memory span exporter and AlwaysSample.
func InitForTest(exporter sdktrace.SpanExporter) (*Providers, error) {
	cfg := Config{
		ServiceName:    "test",
		ServiceVersion: "test",
		Environment:    "test",
		SampleRatio:    1,
	}
	res, err := newResource(cfg)
	if err != nil {
		return nil, err
	}
	tp := sdktrace.NewTracerProvider(
		sdktrace.WithResource(res),
		sdktrace.WithSampler(sdktrace.AlwaysSample()),
		sdktrace.WithSpanProcessor(sdktrace.NewSimpleSpanProcessor(exporter)),
	)
	mp, _, err := newMeterProvider(context.Background(), res, Config{ServiceName: "test", Environment: "test"})
	if err != nil {
		return nil, err
	}
	registerGlobals(tp, mp)
	shutdown := func(ctx context.Context) error {
		return tp.Shutdown(ctx)
	}
	return &Providers{TracerProvider: tp, MeterProvider: mp, Shutdown: shutdown}, nil
}
