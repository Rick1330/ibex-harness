package responsepipeline

import (
	"context"
	"time"
)

// StageLogger records non-critical stage failures (optional; nil disables logging).
type StageLogger interface {
	WarnStageError(ctx context.Context, stage string, err error)
}

// PipelineObserver records stage outcomes (optional; nil disables metrics).
type PipelineObserver interface {
	ObserveStageDuration(stage, result string, seconds float64)
	IncStageFailOpen(stage string)
}

const (
	stageResultSuccess  = "success"
	stageResultError    = "error"
	stageResultFailOpen = "fail_open"
)

// Pipeline runs ordered response stages on non-streaming chat completions.
type Pipeline struct {
	stages []Stage
	log    StageLogger
	obs    PipelineObserver
}

// PipelineOption configures a Pipeline.
type PipelineOption func(*Pipeline)

// WithStageLogger attaches a logger for fail-open stage errors.
func WithStageLogger(log StageLogger) PipelineOption {
	return func(p *Pipeline) {
		p.log = log
	}
}

// WithPipelineObserver attaches metrics for stage execution.
func WithPipelineObserver(obs PipelineObserver) PipelineOption {
	return func(p *Pipeline) {
		p.obs = obs
	}
}

// NewPipeline constructs a pipeline with the given stages.
func NewPipeline(stages []Stage, opts ...PipelineOption) *Pipeline {
	cp := append([]Stage(nil), stages...)
	p := &Pipeline{stages: cp}
	for _, opt := range opts {
		opt(p)
	}
	return p
}

// NewDefaultPipeline returns the production default (single noop stage).
func NewDefaultPipeline(opts ...PipelineOption) *Pipeline {
	return NewPipeline([]Stage{NoopStage{}}, opts...)
}

// Run executes stages in order. Non-critical stage errors fail open; critical stages fail closed.
func (p *Pipeline) Run(ctx context.Context, resp *ChatResponse) (*ChatResponse, error) {
	if p == nil || len(p.stages) == 0 {
		return resp, nil
	}
	current := resp
	for _, stage := range p.stages {
		if err := ctx.Err(); err != nil {
			return nil, err
		}
		next, done, err := p.runStage(ctx, stage, current)
		if done {
			return next, err
		}
		current = next
	}
	return current, nil
}

type stageExec struct {
	stage    Stage
	snapshot *ChatResponse
	start    time.Time
}

func (p *Pipeline) runStage(
	ctx context.Context,
	stage Stage,
	current *ChatResponse,
) (*ChatResponse, bool, error) {
	stageEntry := current.clone()
	start := time.Now()
	next, err := stage.Process(ctx, current)
	if err != nil {
		return p.handleStageError(ctx, stageExec{stage: stage, snapshot: stageEntry, start: start}, err)
	}
	p.recordStage(stage.Name(), stageResultSuccess, start)
	if next != nil {
		return next, false, nil
	}
	return current, false, nil
}

func (p *Pipeline) handleStageError(
	ctx context.Context,
	se stageExec,
	err error,
) (*ChatResponse, bool, error) {
	if isSecurityCritical(se.stage) {
		p.recordStage(se.stage.Name(), stageResultError, se.start)
		return nil, true, err
	}
	if p.log != nil {
		p.log.WarnStageError(ctx, se.stage.Name(), err)
	}
	if p.obs != nil {
		p.obs.IncStageFailOpen(se.stage.Name())
	}
	p.recordStage(se.stage.Name(), stageResultFailOpen, se.start)
	return se.snapshot, false, nil
}

func (p *Pipeline) recordStage(stage, result string, start time.Time) {
	if p == nil || p.obs == nil {
		return
	}
	p.obs.ObserveStageDuration(stage, result, time.Since(start).Seconds())
}

func isSecurityCritical(stage Stage) bool {
	sc, ok := stage.(SecurityCritical)
	return ok && sc.SecurityCritical()
}
