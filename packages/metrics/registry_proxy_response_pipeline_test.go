package metrics

import (
	"math"
	"testing"

	dto "github.com/prometheus/client_model/go"
	"github.com/stretchr/testify/require"
)

func TestUnit_ObserveResponsePipelineStageDuration_NilSafe(t *testing.T) {
	var reg *ProxyRegistry
	reg.ObserveResponsePipelineStageDuration("noop", "success", 0.01)

	reg = &ProxyRegistry{}
	reg.ObserveResponsePipelineStageDuration("noop", "success", 0.01)
}

func labelPairValue(labels []*dto.LabelPair, name string) string {
	for _, lp := range labels {
		if lp.GetName() == name {
			return lp.GetValue()
		}
	}
	return ""
}

func assertDurationFamily(t *testing.T, mfs []*dto.MetricFamily) (uint64, bool, bool) {
	t.Helper()
	var durationCount uint64
	var sawSuccess, sawFailOpen bool
	for _, mf := range mfs {
		if mf.GetName() != "ibex_proxy_response_pipeline_stage_duration_seconds" {
			continue
		}
		require.Equal(t, dto.MetricType_HISTOGRAM, mf.GetType())
		for _, m := range mf.GetMetric() {
			require.Equal(t, "noop", labelPairValue(m.GetLabel(), "stage"))
			switch labelPairValue(m.GetLabel(), "result") {
			case "success":
				sawSuccess = true
			case "fail_open":
				sawFailOpen = true
			default:
				t.Fatalf("unexpected result label %q", labelPairValue(m.GetLabel(), "result"))
			}
			durationCount += m.GetHistogram().GetSampleCount()
		}
	}
	return durationCount, sawSuccess, sawFailOpen
}

func assertFailOpenFamily(t *testing.T, mfs []*dto.MetricFamily) uint64 {
	t.Helper()
	var failOpenCount uint64
	for _, mf := range mfs {
		if mf.GetName() != "ibex_proxy_response_pipeline_stage_fail_open_total" {
			continue
		}
		for _, m := range mf.GetMetric() {
			require.Equal(t, "noop", labelPairValue(m.GetLabel(), "stage"))
			failOpenCount += uint64(m.GetCounter().GetValue())
		}
	}
	return failOpenCount
}

func TestUnit_ObserveResponsePipelineStageDuration_Registered(t *testing.T) {
	reg := NewProxy("response-pipeline-metrics-test")
	reg.ObserveResponsePipelineStageDuration("noop", "success", 0.001)
	reg.ObserveResponsePipelineStageDuration("noop", "fail_open", 0.002)
	reg.IncResponsePipelineStageFailOpen("noop")

	mfs, err := reg.Gatherer().Gather()
	require.NoError(t, err)

	durationCount, sawSuccess, sawFailOpen := assertDurationFamily(t, mfs)
	failOpenCount := assertFailOpenFamily(t, mfs)

	require.True(t, sawSuccess)
	require.True(t, sawFailOpen)
	require.Equal(t, uint64(2), durationCount)
	require.Equal(t, uint64(1), failOpenCount)
}

func TestUnit_ObserveResponsePipelineStageDuration_RejectsInvalidSeconds(t *testing.T) {
	reg := NewProxy("response-pipeline-metrics-invalid-test")
	reg.ObserveResponsePipelineStageDuration("noop", "success", -1)
	reg.ObserveResponsePipelineStageDuration("noop", "success", math.NaN())
	reg.ObserveResponsePipelineStageDuration("noop", "success", math.Inf(1))
	reg.ObserveResponsePipelineStageDuration("noop", "success", 0.001)

	mfs, err := reg.Gatherer().Gather()
	require.NoError(t, err)

	durationCount, sawSuccess, sawFailOpen := assertDurationFamily(t, mfs)
	require.True(t, sawSuccess)
	require.False(t, sawFailOpen)
	require.Equal(t, uint64(1), durationCount)
}

func TestUnit_IncResponsePipelineStageFailOpen_NilSafe(t *testing.T) {
	var reg *ProxyRegistry
	reg.IncResponsePipelineStageFailOpen("noop")

	reg = &ProxyRegistry{}
	reg.IncResponsePipelineStageFailOpen("noop")
}
