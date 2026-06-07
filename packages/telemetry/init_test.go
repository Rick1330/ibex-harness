package telemetry_test

import (
	"context"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/telemetry"
)

func TestTelemetry_NoopOnEmptyEndpoint(t *testing.T) {
	providers, err := telemetry.Init(context.Background(), telemetry.Config{
		ServiceName: "proxy",
	})
	if err != nil {
		t.Fatalf("Init: %v", err)
	}
	if providers.TracerProvider == nil || providers.MeterProvider == nil {
		t.Fatal("expected non-nil providers")
	}
}

func TestTelemetry_Shutdown(t *testing.T) {
	providers, err := telemetry.Init(context.Background(), telemetry.Config{
		ServiceName: "proxy",
	})
	if err != nil {
		t.Fatalf("Init: %v", err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := providers.Shutdown(ctx); err != nil {
		t.Fatalf("Shutdown: %v", err)
	}
}
