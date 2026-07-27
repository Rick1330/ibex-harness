package session

import (
	"context"
	"errors"
	"time"

	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/packages/reqid"
	pkgsession "github.com/Rick1330/ibex-harness/packages/session"
	httptrace "github.com/Rick1330/ibex-harness/services/proxy/internal/http/trace"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/llm"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/sessioncache"
)

// WantCheckpoint is true for successful or streaming turns with a durable session.
// Provider-failure traces (non-stream, incomplete) must not append empty checkpoints.
func WantCheckpoint(deps LifecycleDeps, rs Resolved, in CheckpointInput, outcome httptrace.RequestOutcome) bool {
	if deps.Store == nil {
		return false
	}
	if !rs.Durable() {
		return false
	}
	return outcome.IsComplete || in.IsStreaming
}

// BuildCheckpointParams maps a resolved session + turn into AppendCheckpoint params.
func BuildCheckpointParams(rs Resolved, in CheckpointInput, requestID string) pkgsession.CheckpointParams {
	inputTok, outputTok := usageTokens(in.Usage)
	return pkgsession.CheckpointParams{
		SessionID: rs.SessionID, OrgID: rs.OrgID, AgentID: rs.AgentID,
		TurnIndex: rs.TurnIndex, RequestID: requestID,
		MessagesHash: hashLLMMessages(in.Messages),
		InputTokens:  inputTok, OutputTokens: outputTok,
		Model: in.Model, Provider: in.Provider,
		CompletionHash:    pkgsession.HashText(in.CompletionText),
		LatencyMs:         int(in.Latency / time.Millisecond),
		ProviderRequestID: in.ProviderReqID,
		IsStreaming:       in.IsStreaming, IsComplete: in.IsComplete,
	}
}

func usageTokens(u *provider.Usage) (int, int) {
	if u == nil {
		return 0, 0
	}
	return u.InputTokens, u.OutputTokens
}

func hashLLMMessages(msgs []llm.Message) string {
	out := make([]pkgsession.MessageForHash, len(msgs))
	for i, m := range msgs {
		out[i] = pkgsession.MessageForHash{Role: m.Role, Content: m.Content}
	}
	return pkgsession.HashMessages(out)
}

// RunCheckpoint appends a checkpoint (with duplicate-turn retry) off the hot path.
func (d LifecycleDeps) RunCheckpoint(params pkgsession.CheckpointParams, externalID string) {
	ctx, cancel := context.WithTimeout(context.Background(), CheckpointTaskTimeout)
	defer cancel()
	if params.RequestID != "" {
		ctx = reqid.WithRequestID(ctx, params.RequestID)
	}
	err := d.Store.AppendCheckpoint(ctx, params)
	if err == nil {
		d.cacheSet(ctx, sessioncache.LookupKey{
			OrgID: params.OrgID, AgentID: params.AgentID, ExternalID: externalID,
		}, sessioncache.Entry{SessionID: params.SessionID, TurnCount: params.TurnIndex + 1})
		return
	}
	if errors.Is(err, pkgsession.ErrDuplicateTurn) {
		d.retryCheckpoint(ctx, params, externalID)
		return
	}
	d.warnCheckpoint(ctx, params, err)
}

func (d LifecycleDeps) retryCheckpoint(
	ctx context.Context,
	params pkgsession.CheckpointParams,
	externalID string,
) {
	if d.Cache != nil {
		d.Cache.Invalidate(ctx, sessioncache.LookupKey{
			OrgID: params.OrgID, AgentID: params.AgentID, ExternalID: externalID,
		})
	}
	sess, err := d.Store.GetOrCreate(ctx, pkgsession.GetOrCreateParams{
		OrgID: params.OrgID, AgentID: params.AgentID, ExternalID: externalID,
		Model: params.Model, Provider: params.Provider,
	})
	if err != nil {
		d.warnCheckpoint(ctx, params, err)
		return
	}
	params.SessionID = sess.ID
	params.TurnIndex = sess.TurnCount
	if err := d.Store.AppendCheckpoint(ctx, params); err != nil {
		d.warnCheckpoint(ctx, params, err)
		return
	}
	d.cacheSet(ctx, sessioncache.LookupKey{
		OrgID: params.OrgID, AgentID: params.AgentID, ExternalID: externalID,
	}, sessioncache.Entry{SessionID: sess.ID, TurnCount: params.TurnIndex + 1})
}

func (d LifecycleDeps) warnCheckpoint(ctx context.Context, params pkgsession.CheckpointParams, err error) {
	if d.Log == nil {
		return
	}
	d.Log.WarnCtx(ctx, "session checkpoint failed",
		"error", err.Error(),
		"session_id", params.SessionID.String(),
		"turn_index", params.TurnIndex,
	)
}
