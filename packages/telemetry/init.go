package telemetry

import (
	"context"
	"errors"
	"fmt"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/propagation"
	sdkmetric "go.opentelemetry.io/otel/sdk/metric"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
)

// Providers holds initialized OTel providers and their shutdown function.
type Providers struct {
	TracerProvider *sdktrace.TracerProvider
	MeterProvider  *sdkmetric.MeterProvider
	Shutdown       func(ctx context.Context) error
}

// Init initialises tracer and meter providers from cfg.
// Uses no-op export when OTLPEndpoint is empty.
func Init(ctx context.Context, cfg Config) (*Providers, error) {
	if err := validateConfig(&cfg); err != nil {
		return nil, err
	}

	res, err := newResource(cfg)
	if err != nil {
		return nil, fmt.Errorf("telemetry resource: %w", err)
	}

	tp, traceExpShutdown, err := newTraceProvider(ctx, res, cfg)
	if err != nil {
		return nil, fmt.Errorf("telemetry tracer: %w", err)
	}
	mp, metricExpShutdown, err := newMeterProvider(ctx, res, cfg)
	if err != nil {
		return nil, fmt.Errorf("telemetry meter: %w", err)
	}

	otel.SetTracerProvider(tp)
	otel.SetMeterProvider(mp)
	otel.SetTextMapPropagator(propagation.NewCompositeTextMapPropagator(
		propagation.TraceContext{},
		propagation.Baggage{},
	))

	shutdown := func(ctx context.Context) error {
		var errs []error
		if traceExpShutdown != nil {
			errs = append(errs, traceExpShutdown(ctx))
		}
		if metricExpShutdown != nil {
			errs = append(errs, metricExpShutdown(ctx))
		}
		errs = append(errs, tp.Shutdown(ctx), mp.Shutdown(ctx))
		return errors.Join(errs...)
	}

	return &Providers{
		TracerProvider: tp,
		MeterProvider:  mp,
		Shutdown:       shutdown,
	}, nil
}

func validateConfig(cfg *Config) error {
	if cfg.ServiceName == "" {
		return errors.New("telemetry: ServiceName is required")
	}
	if cfg.ServiceVersion == "" {
		cfg.ServiceVersion = "dev"
	}
	if cfg.Environment == "" {
		cfg.Environment = "development"
	}
	if cfg.SampleRatio <= 0 {
		cfg.SampleRatio = 0.01
	}
	return nil
}
