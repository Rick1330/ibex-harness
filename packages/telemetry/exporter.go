package telemetry

import (
	"context"

	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc"
	sdkmetric "go.opentelemetry.io/otel/sdk/metric"
	"go.opentelemetry.io/otel/sdk/resource"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
)

func newTraceProvider(ctx context.Context, res *resource.Resource, cfg Config) (*sdktrace.TracerProvider, func(context.Context) error, error) {
	opts := []sdktrace.TracerProviderOption{
		sdktrace.WithResource(res),
		sdktrace.WithSampler(parentBasedSampler(cfg.SampleRatio)),
	}
	var shutdown func(context.Context) error
	if cfg.OTLPEndpoint != "" {
		exp, err := otlptracegrpc.New(ctx,
			otlptracegrpc.WithEndpoint(cfg.OTLPEndpoint),
			otlptracegrpc.WithInsecure(),
		)
		if err != nil {
			return nil, nil, err
		}
		shutdown = exp.Shutdown
		opts = append(opts, sdktrace.WithBatcher(exp))
	}
	return sdktrace.NewTracerProvider(opts...), shutdown, nil
}

func newMeterProvider(ctx context.Context, res *resource.Resource, cfg Config) (*sdkmetric.MeterProvider, func(context.Context) error, error) {
	// IBEX application metrics are Prometheus-pull (/metrics). OTLP metric export is
	// intentionally disabled so a traces-only collector (Tempo) is not probed for
	// MetricsService. Keep a MeterProvider for API completeness / future bridges.
	_ = ctx
	_ = cfg
	return sdkmetric.NewMeterProvider(sdkmetric.WithResource(res)), nil, nil
}
