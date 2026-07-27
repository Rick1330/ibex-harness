package session

import (
	"context"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	httptrace "github.com/Rick1330/ibex-harness/services/proxy/internal/http/trace"
	"github.com/google/uuid"
)

// CaptureTraceSnapshot builds an AssembleInput from injected meta + turn data.
func CaptureTraceSnapshot(
	meta SnapshotMeta,
	in CheckpointInput,
	outcome httptrace.RequestOutcome,
) (httptrace.AssembleInput, bool) {
	if meta.RequestID == "" || meta.OrgID == uuid.Nil || meta.AgentID == uuid.Nil {
		return httptrace.AssembleInput{}, false
	}
	completed := time.Now().UTC()
	requested := completed
	if !meta.RequestedAt.IsZero() {
		requested = meta.RequestedAt.UTC()
	}
	status := outcome.StatusCode
	if status == 0 && outcome.IsComplete {
		status = 200
	}
	streaming := in.IsStreaming
	if outcome.StreamRequested {
		streaming = true
	}
	return httptrace.AssembleInput{
		RequestID: meta.RequestID,
		OrgID:     meta.OrgID,
		AgentID:   meta.AgentID,
		SessionID: meta.SessionID,
		Model:     in.Model,
		Provider:  in.Provider,
		Streaming: streaming,
		Usage:     in.Usage,
		Timings: httptrace.RequestTimings{
			AuthMs:       meta.AuthMs,
			DirectiveMs:  meta.DirectiveMs,
			ProviderTTFB: in.Latency,
			RequestedAt:  requested,
			CompletedAt:  completed,
		},
		Outcome: httptrace.RequestOutcome{
			StatusCode: status,
			IsComplete: outcome.IsComplete,
			ErrorCode:  outcome.ErrorCode,
		},
	}, true
}

// EmitTrace writes an assembled row; failures are logged and never surface to clients.
func EmitTrace(w httptrace.TraceWriter, log *logger.Logger, snap httptrace.AssembleInput) {
	if w == nil {
		return
	}
	err := w.Write(httptrace.Assemble(snap))
	if err == nil || log == nil {
		return
	}
	log.WarnCtx(context.Background(), "trace emit failed",
		"error", err,
		"request_id", snap.RequestID,
		"org_id", snap.OrgID.String(),
	)
}

// EnqueuePostResponse runs optional checkpoint + trace emit on the bounded pool.
func EnqueuePostResponse(job PostResponseJob) {
	if !job.DoCheckpoint && !job.DoTrace {
		return
	}
	run := func() {
		if job.DoCheckpoint {
			job.Deps.RunCheckpoint(job.Params, job.ExternalID)
		}
		if job.DoTrace {
			EmitTrace(job.TraceWriter, job.Log, job.Snap)
		}
	}
	if job.Deps.Pool != nil {
		job.Deps.Pool.Submit(run)
		return
	}
	run()
}

// PreparePostResponse decides checkpoint/trace work and builds a submit job.
func PreparePostResponse(
	deps LifecycleDeps,
	tw httptrace.TraceWriter,
	log *logger.Logger,
	rs Resolved,
	meta SnapshotMeta,
	in CheckpointInput,
	outcome httptrace.RequestOutcome,
) PostResponseJob {
	snap, snapOK := CaptureTraceSnapshot(meta, in, outcome)
	doCheckpoint := WantCheckpoint(deps, rs, in, outcome)
	doTrace := snapOK && httptrace.EffectiveWriter(tw) != nil
	job := PostResponseJob{
		Deps: deps, In: in, Snap: snap, SnapOK: snapOK,
		DoCheckpoint: doCheckpoint, DoTrace: doTrace,
		TraceWriter: tw, Log: log,
	}
	if doCheckpoint {
		job.Params = BuildCheckpointParams(rs, in, meta.RequestID)
		job.ExternalID = rs.ExternalID
	}
	return job
}
