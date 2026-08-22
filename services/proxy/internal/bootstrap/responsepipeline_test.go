package bootstrap

import (
	"bytes"
	"context"
	"errors"
	"log/slog"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/packages/provider/mockllm"
	"github.com/Rick1330/ibex-harness/packages/responsepipeline"
	"github.com/stretchr/testify/require"
)

func TestUnit_BuildResponsePipeline_DefaultNoop(t *testing.T) {
	p := buildResponsePipeline(logger.Discard("proxy"), nil)
	require.NotNil(t, p)

	chat, err := responsepipeline.Decode([]byte(mockllm.MockJSONBody()))
	require.NoError(t, err)
	out, err := p.Run(context.Background(), chat)
	require.NoError(t, err)
	wire, err := out.Bytes()
	require.NoError(t, err)
	require.Equal(t, mockllm.MockJSONBody(), string(wire))
}

func TestUnit_BuildResponsePipeline_WiresObserver(t *testing.T) {
	reg := metrics.NewProxy("response-pipeline-test")
	p := buildResponsePipeline(logger.Discard("proxy"), reg)
	require.NotNil(t, p)

	chat, err := responsepipeline.Decode([]byte(mockllm.MockJSONBody()))
	require.NoError(t, err)
	_, err = p.Run(context.Background(), chat)
	require.NoError(t, err)
}

func TestUnit_BuildResponsePipeline_WiresObserverFailOpen(t *testing.T) {
	reg := metrics.NewProxy("response-pipeline-test")
	p := responsepipeline.NewPipeline([]responsepipeline.Stage{stubFailStage{}},
		responsepipeline.WithStageLogger(proxyStageLogger{log: logger.Discard("proxy")}),
		responsepipeline.WithPipelineObserver(proxyPipelineObserver{reg: reg}),
	)
	chat, err := responsepipeline.Decode([]byte(mockllm.MockJSONBody()))
	require.NoError(t, err)
	_, err = p.Run(context.Background(), chat)
	require.NoError(t, err)
}

type stubFailStage struct{}

func (stubFailStage) Name() string { return "fail-open-stage" }

func (stubFailStage) Process(_ context.Context, _ *responsepipeline.ChatResponse) (*responsepipeline.ChatResponse, error) {
	return nil, errors.New("fail-open")
}

func TestUnit_ProxyStageObserver_NilRegistryNoPanic(t *testing.T) {
	require.NotPanics(t, func() {
		var obs proxyPipelineObserver
		obs.ObserveStageDuration("noop", "success", 0.01)
		obs.IncStageFailOpen("noop")
	})
}

func TestUnit_ProxyStageLogger_NilLogNoPanic(t *testing.T) {
	require.NotPanics(t, func() {
		proxyStageLogger{log: nil}.WarnStageError(context.Background(), "stage", errors.New("boom"))
	})
}

func TestUnit_ProxyStageLogger_NilErrNoPanic(t *testing.T) {
	require.NotPanics(t, func() {
		proxyStageLogger{log: logger.Discard("proxy")}.WarnStageError(context.Background(), "stage", nil)
	})
}

func TestUnit_ProxyStageLogger_LogsStageNotContent(t *testing.T) {
	var buf bytes.Buffer
	log, err := logger.New(logger.Config{
		Service: "proxy",
		Level:   slog.LevelWarn,
		Writer:  &buf,
	})
	require.NoError(t, err)
	proxyStageLogger{log: log}.WarnStageError(context.Background(), "redact", errors.New("stage failed"))
	out := buf.String()
	require.Contains(t, out, "redact")
	require.Contains(t, out, "stage failed")
	require.NotContains(t, out, "assistant")
	require.NotContains(t, out, "message.content")
}
