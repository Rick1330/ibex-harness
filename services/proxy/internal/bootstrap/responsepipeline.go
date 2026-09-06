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

func (p proxyStageLogger) WarnStageError(ctx context.Context, stage string, _ error) {
	if p.log == nil {
		return
	}
	p.log.WarnCtx(ctx, "response pipeline stage failed; fail-open",
		"stage", stage,
		"error_class", "stage_error",
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

func buildResponsePipeline(log *logger.Logger, reg *metrics.ProxyRegistry, embedMetadata bool) *responsepipeline.Pipeline {
	opts := []responsepipeline.PipelineOption{
		responsepipeline.WithStageLogger(proxyStageLogger{log: log}),
	}
	if reg != nil {
		opts = append(opts, responsepipeline.WithPipelineObserver(proxyPipelineObserver{reg: reg}))
	}
	stages := []responsepipeline.Stage{responsepipeline.NoopStage{}}
	// Conditionally register IBEXMetadataStage (3.5.D.3). When the flag is off the
	// stage is absent entirely so Process is never invoked; when on, the stage
	// still no-ops per-request if Assemble was not attempted (dirty untouched).
	if embedMetadata {
		stages = append(stages, responsepipeline.IBEXMetadataStage{})
	}
	return responsepipeline.NewPipeline(stages, opts...)
}
