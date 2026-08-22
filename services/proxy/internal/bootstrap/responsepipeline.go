package bootstrap

import (
	"context"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/packages/responsepipeline"
)

type proxyStageLogger struct {
	log *logger.Logger
}

func (p proxyStageLogger) WarnStageError(ctx context.Context, stage string, err error) {
	if p.log == nil || err == nil {
		return
	}
	p.log.WarnCtx(ctx, "response pipeline stage failed; fail-open",
		"stage", stage,
		"error", err.Error(),
	)
}

type proxyPipelineObserver struct {
	reg *metrics.ProxyRegistry
}

func (o proxyPipelineObserver) ObserveStageDuration(stage, result string, seconds float64) {
	if o.reg == nil {
		return
	}
	o.reg.ObserveResponsePipelineStageDuration(stage, result, seconds)
}

func (o proxyPipelineObserver) IncStageFailOpen(stage string) {
	if o.reg == nil {
		return
	}
	o.reg.IncResponsePipelineStageFailOpen(stage)
}

func buildResponsePipeline(log *logger.Logger, reg *metrics.ProxyRegistry) *responsepipeline.Pipeline {
	opts := []responsepipeline.PipelineOption{
		responsepipeline.WithStageLogger(proxyStageLogger{log: log}),
	}
	if reg != nil {
		opts = append(opts, responsepipeline.WithPipelineObserver(proxyPipelineObserver{reg: reg}))
	}
	return responsepipeline.NewDefaultPipeline(opts...)
}
