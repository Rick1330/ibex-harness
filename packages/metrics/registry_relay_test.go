package metrics

import (
	"testing"
)

func TestRelayMetricsEndpoint_RequiredMetrics(t *testing.T) {
	t.Parallel()
	reg := NewRelay("test-relay")
	seedRelaySamples(reg)
	assertRequiredMetrics(t, reg.Gatherer(), RelayRequiredMetricNames)
}

func TestUnit_BoundRelayLabel(t *testing.T) {
	t.Parallel()
	if got := boundRelayLabel(RelayBatchOK, relayBatchResults); got != RelayBatchOK {
		t.Fatalf("got %q", got)
	}
	if got := boundRelayLabel("weird", relayBatchResults); got != RelayBatchError {
		t.Fatalf("fallback got %q", got)
	}
	if got := boundRelayLabel(RelayDeliveryError, relayDeliveryResults); got != RelayDeliveryError {
		t.Fatalf("got %q", got)
	}
	if got := boundRelayLabel("weird", relayDeliveryResults); got != RelayDeliveryError {
		t.Fatalf("fallback got %q", got)
	}
	if got := boundRelayLabel(RelayFenceStale, relayFenceOutcomes); got != RelayFenceStale {
		t.Fatalf("got %q", got)
	}
	if got := boundRelayLabel("weird", relayFenceOutcomes); got != RelayFenceError {
		t.Fatalf("fallback got %q", got)
	}
}

func seedRelaySamples(reg *RelayRegistry) {
	reg.ObserveBatch(RelayBatchOK, 0.001)
	reg.ObserveBatch(RelayBatchError, 0.002)
	reg.ObserveBatch("not-a-real-result", 0.001)
	reg.AddClaimed(1)
	reg.AddClaimed(0)
	reg.AddDelivered(1)
	reg.AddRetried(1)
	reg.AddDeadLettered(1)
	reg.AddRecovered(1)
	reg.ObserveDelivery(RelayDeliveryOK, 0.001)
	reg.ObserveDelivery(RelayDeliveryError, 0.001)
	reg.ObserveDelivery("weird", 0.001)
	reg.ObserveFenceCheck(RelayFenceAlive, 0.001)
	reg.ObserveFenceCheck(RelayFenceTombstoned, 0.001)
	reg.ObserveFenceCheck(RelayFenceStale, 0.001)
	reg.ObserveFenceCheck(RelayFenceNotFound, 0.001)
	reg.ObserveFenceCheck(RelayFenceError, 0.001)
	reg.ObserveFenceCheck("weird", 0.001)
}
