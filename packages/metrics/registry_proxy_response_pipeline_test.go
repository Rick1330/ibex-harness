package metrics

import (
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

func TestUnit_ObserveResponsePipelineStageDuration_Registered(t *testing.T) {
	reg := NewProxy("response-pipeline-metrics-test")
	reg.ObserveResponsePipelineStageDuration("noop", "success", 0.001)
	reg.ObserveResponsePipelineStageDuration("noop", "fail_open", 0.002)
	reg.IncResponsePipelineStageFailOpen("noop")

	mfs, err := reg.Gatherer().Gather()
	require.NoError(t, err)

	var durationCount, failOpenCount uint64
	for _, mf := range mfs {
		switch mf.GetName() {
		case "ibex_proxy_response_pipeline_stage_duration_seconds":
			for _, m := range mf.GetMetric() {
				require.Equal(t, dto.MetricType_HISTOGRAM, mf.GetType())
				durationCount += m.GetHistogram().GetSampleCount()
			}
		case "ibex_proxy_response_pipeline_stage_fail_open_total":
			for _, m := range mf.GetMetric() {
				failOpenCount += uint64(m.GetCounter().GetValue())
			}
		}
	}
	require.Equal(t, uint64(2), durationCount)
	require.Equal(t, uint64(1), failOpenCount)
}

func TestUnit_IncResponsePipelineStageFailOpen_NilSafe(t *testing.T) {
	var reg *ProxyRegistry
	reg.IncResponsePipelineStageFailOpen("noop")
}
