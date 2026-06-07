package telemetry

import (
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
)

func parentBasedSampler(ratio float64) sdktrace.Sampler {
	if ratio <= 0 {
		ratio = 0.01
	}
	return sdktrace.ParentBased(sdktrace.TraceIDRatioBased(ratio))
}
