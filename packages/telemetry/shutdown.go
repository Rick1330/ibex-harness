package telemetry

import (
	"context"
	"errors"

	sdkmetric "go.opentelemetry.io/otel/sdk/metric"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
)

func buildShutdown(
	tp *sdktrace.TracerProvider,
	mp *sdkmetric.MeterProvider,
	traceExpShutdown func(context.Context) error,
	metricExpShutdown func(context.Context) error,
) func(context.Context) error {
	return func(ctx context.Context) error {
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
}
