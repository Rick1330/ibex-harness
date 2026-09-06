package session

import (
	"context"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/reqid"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/extractionbuffer"
	httptrace "github.com/Rick1330/ibex-harness/services/proxy/internal/http/trace"
	"github.com/google/uuid"
)

// CaptureTraceArgs groups identity + turn data for CaptureTraceSnapshot.
type CaptureTraceArgs struct {
	Meta    SnapshotMeta
	In      CheckpointInput
	Outcome httptrace.RequestOutcome
}

// CaptureTraceSnapshot builds an AssembleInput from injected meta + turn data.
func CaptureTraceSnapshot(args CaptureTraceArgs) (httptrace.AssembleInput, bool) {
	if !snapshotMetaValid(args.Meta) {
		return httptrace.AssembleInput{}, false
	}
	completed := time.Now().UTC()
	return httptrace.AssembleInput{
		RequestID: args.Meta.RequestID,
		OrgID:     args.Meta.OrgID,
		AgentID:   args.Meta.AgentID,
		SessionID: args.Meta.SessionID,
		Model:     args.In.Model,
		Provider:  args.In.Provider,
		Streaming: resolveStreaming(args.In, args.Outcome),
		Usage:     args.In.Usage,
		Timings: httptrace.RequestTimings{
			AuthMs:       args.Meta.AuthMs,
			DirectiveMs:  args.Meta.DirectiveMs,
			ProviderTTFB: args.In.Latency,
			RequestedAt:  requestedAtOr(args.Meta, completed),
			CompletedAt:  completed,
		},
		Outcome: httptrace.RequestOutcome{
			StatusCode: defaultCompleteStatus(args.Outcome),
			IsComplete: args.Outcome.IsComplete,
			ErrorCode:  args.Outcome.ErrorCode,
		},
	}, true
}

func snapshotMetaValid(meta SnapshotMeta) bool {
	if meta.RequestID == "" {
		return false
	}
	if meta.OrgID == uuid.Nil {
		return false
	}
	return meta.AgentID != uuid.Nil
}

func requestedAtOr(meta SnapshotMeta, completed time.Time) time.Time {
	if meta.RequestedAt.IsZero() {
		return completed
	}
	return meta.RequestedAt.UTC()
}

func defaultCompleteStatus(outcome httptrace.RequestOutcome) uint16 {
	if outcome.StatusCode != 0 {
		return outcome.StatusCode
	}
	if outcome.IsComplete {
		return 200
	}
	return 0
}

func resolveStreaming(in CheckpointInput, outcome httptrace.RequestOutcome) bool {
	if outcome.StreamRequested {
		return true
	}
	return in.IsStreaming
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
	ctx := context.Background()
	if snap.RequestID != "" {
		ctx = reqid.WithRequestID(ctx, snap.RequestID)
	}
	log.WarnCtx(ctx, "trace emit failed",
		"error", err,
		"request_id", snap.RequestID,
		"org_id", snap.OrgID.String(),
	)
}

// EnqueuePostResponse runs optional checkpoint + turn buffer + trace emit.
// Buffer append runs synchronously so terminate cannot race an empty drain;
// checkpoint and trace remain on the bounded pool.
func EnqueuePostResponse(job PostResponseJob) {
	flushBuffer(job)
	runDeferredPostResponse(job)
}

func flushBuffer(job PostResponseJob) {
	if !job.DoBuffer {
		return
	}
	job.Deps.appendExtractionTurns(job.BufferKey, job.BufferTurns)
}

func runDeferredPostResponse(job PostResponseJob) {
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

// PreparePostResponseInput groups deps and turn data for PreparePostResponse.
type PreparePostResponseInput struct {
	Deps     LifecycleDeps
	Writer   httptrace.TraceWriter
	Log      *logger.Logger
	Resolved Resolved
	Meta     SnapshotMeta
	In       CheckpointInput
	Outcome  httptrace.RequestOutcome
}

// PreparePostResponse decides checkpoint/trace/buffer work and builds a submit job.
func PreparePostResponse(in PreparePostResponseInput) PostResponseJob {
	snap, snapOK := CaptureTraceSnapshot(CaptureTraceArgs{
		Meta: in.Meta, In: in.In, Outcome: in.Outcome,
	})
	doCheckpoint := WantCheckpoint(in.Deps, in.Resolved, in.In, in.Outcome)
	doTrace := snapOK && httptrace.EffectiveWriter(in.Writer) != nil
	doBuffer := wantExtractionBuffer(in)
	job := PostResponseJob{
		Deps: in.Deps, In: in.In, Snap: snap, SnapOK: snapOK,
		DoCheckpoint: doCheckpoint, DoTrace: doTrace, DoBuffer: doBuffer,
		TraceWriter: in.Writer, Log: in.Log,
	}
	if doCheckpoint {
		job.Params = BuildCheckpointParams(in.Resolved, in.In, in.Meta.RequestID)
		job.ExternalID = in.Resolved.ExternalID
	}
	if doBuffer {
		job.BufferKey = extractionbuffer.LookupKey{
			OrgID: in.Meta.OrgID, AgentID: in.Meta.AgentID, ExternalID: in.Resolved.ExternalID,
		}
		job.BufferTurns = extractionTurnsFromInput(in.Resolved.TurnIndex, in.In)
	}
	return job
}

// wantExtractionBuffer is true for successful/streaming turns when tenant + sticky
// ids are present — including sticky-only sessions that skip durable checkpoints.
func wantExtractionBuffer(in PreparePostResponseInput) bool {
	if in.Deps.TurnBuffer == nil {
		return false
	}
	if in.Meta.OrgID == uuid.Nil || in.Meta.AgentID == uuid.Nil {
		return false
	}
	if in.Resolved.ExternalID == "" {
		return false
	}
	return in.Outcome.IsComplete || in.In.IsStreaming
}

func extractionTurnsFromInput(turnIndex int, in CheckpointInput) []extractionbuffer.Turn {
	lastUser := ""
	for i := len(in.Messages) - 1; i >= 0; i-- {
		if in.Messages[i].Role == "user" && in.Messages[i].Content != "" {
			lastUser = in.Messages[i].Content
			break
		}
	}
	return extractionbuffer.TurnsFromChat(turnIndex, lastUser, in.CompletionText)
}
