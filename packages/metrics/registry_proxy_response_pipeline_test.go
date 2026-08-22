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

func durationMetrics(mfs []*dto.MetricFamily) []*dto.Metric {
	for _, mf := range mfs {
		if mf.GetName() == "ibex_proxy_response_pipeline_stage_duration_seconds" {
			return mf.GetMetric()
		}
	}
	return nil
}

func noopDurationResult(t *testing.T, m *dto.Metric) (string, uint64) {
	t.Helper()
	require.Equal(t, "noop", labelPairValue(m.GetLabel(), "stage"))
	result := labelPairValue(m.GetLabel(), "result")
	require.Contains(t, []string{"success", "fail_open"}, result)
	return result, m.GetHistogram().GetSampleCount()
}

func sumNoopDurationResults(t *testing.T, metrics []*dto.Metric) (uint64, bool, bool) {
	t.Helper()
	var durationCount uint64
	var sawSuccess, sawFailOpen bool
	for _, m := range metrics {
		result, count := noopDurationResult(t, m)
		durationCount += count
		sawSuccess = sawSuccess || result == "success"
		sawFailOpen = sawFailOpen || result == "fail_open"
	}
	return durationCount, sawSuccess, sawFailOpen
}

func assertDurationFamily(t *testing.T, mfs []*dto.MetricFamily) (uint64, bool, bool) {
	t.Helper()
	return sumNoopDurationResults(t, durationMetrics(mfs))
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
