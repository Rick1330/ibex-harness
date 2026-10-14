package session

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"

	apierror "github.com/Rick1330/ibex-harness/packages/apierror"
	"github.com/Rick1330/ibex-harness/packages/evidenceoutbox"
	"github.com/google/uuid"
)

// EvidenceAckProfile is selected by an operation's capture policy. A profile
// may permit an explicitly uncertified 202 only when PostgreSQL reconciliation
// proves a durable retryable outbox row. Required remains descriptive; the zero
// value never turns a missing/unknown write into success.
type EvidenceAckProfile struct {
	Required         bool
	AllowUncertified bool
}

// PersistEvidenceForProfile is the synchronous acknowledgement boundary. The
// legacy post-response finalizer uses it internally but does not rewrite a
// response already sent to the chat client.
func PersistEvidenceForProfile(ctx context.Context, p EvidencePersister, in evidenceoutbox.RunInput, profile EvidenceAckProfile) EvidencePersistOutcome {
	out := EvidencePersistOutcome{Input: in}
	p = EffectiveEvidence(p)
	if p == nil {
		out.Status = EvidenceAckUnavailable
		out.Err = errors.New("evidence persister is unavailable")
		return out
	}
	result, err := p.PersistRun(ctx, in)
	if isDurablePersistResult(result, err) {
		out.Result = result
		out.Status = EvidenceAckDurable
		if result.Replayed {
			out.Status = EvidenceAckReplay
		}
		return out
	}
	unknown := err == nil
	if unknown {
		err = errors.New("evidence commit outcome is unknown")
	}
	out.Err = err
	reconcileCtx, cancel := context.WithTimeout(context.WithoutCancel(ctx), CheckpointTaskTimeout)
	defer cancel()
	if reconciled, ok := reconcileEvidenceFailure(reconcileCtx, p, in, profile, out); ok {
		return reconciled
	}
	if unknown {
		out.Status = EvidenceAckUnknown
	} else {
		out.Status = EvidenceAckUnavailable
	}
	return out
}

func isDurablePersistResult(result evidenceoutbox.PersistResult, err error) bool {
	return err == nil && result.RunID != uuid.Nil && len(result.OutboxIDs) != 0
}

func reconcileEvidenceFailure(ctx context.Context, p EvidencePersister, in evidenceoutbox.RunInput, profile EvidenceAckProfile, out EvidencePersistOutcome) (EvidencePersistOutcome, bool) {
	source, ok := p.(evidenceoutbox.ReconciliationSource)
	if !ok {
		return out, false
	}
	proof, err := source.ReconcileRun(ctx, in)
	if err != nil || !proof.Matches(in) {
		return out, false
	}
	out.Proof = &proof
	out.Result = evidenceoutbox.PersistResult{
		RunID: proof.RunID, OutboxIDs: append([]uuid.UUID(nil), proof.OutboxIDs...),
		AggregateID: proof.RequestID, Replayed: true,
	}
	if proof.AllDelivered(in) {
		out.Status = EvidenceAckReplay
		out.Err = nil
		return out, true
	}
	if profile.AllowUncertified && proof.HasDurableRetry(in) {
		out.Status = EvidenceAckUncertified
		return out, true
	}
	return out, false
}

// EvidenceAckHTTP implements the owner-approved mapping. Uncertified is 202
// only if the attached, request-bound proof verifies at least one durable retry
// row; unknown, failed, and unproved uncertified outcomes all fail closed to 503.
func EvidenceAckHTTP(out EvidencePersistOutcome) (int, apierror.Code) {
	switch out.Status {
	case EvidenceAckDurable:
		if validPersistResult(out.Result) {
			return http.StatusOK, ""
		}
	case EvidenceAckReplay:
		if validPersistResult(out.Result) {
			return http.StatusOK, ""
		}
	case EvidenceAckUncertified:
		if out.Proof != nil && out.Proof.HasDurableRetry(out.Input) &&
			out.Proof.RunID == out.Result.RunID && sameUUIDList(out.Proof.OutboxIDs, out.Result.OutboxIDs) {
			return http.StatusAccepted, ""
		}
	}
	return http.StatusServiceUnavailable, apierror.CodeEvidenceUnavailable
}

// WriteEvidenceAck writes the stable success/accepted body or payload-free 503
// envelope. It is an adapter for a response-bound operation; it must not be
// called after an unrelated response has already been committed.
func WriteEvidenceAck(w http.ResponseWriter, out EvidencePersistOutcome, requestID string) {
	status, code := EvidenceAckHTTP(out)
	if code != "" {
		apierror.WriteStatus(w, status, code, "Evidence is temporarily unavailable", requestID, apierror.WriteOpts{})
		return
	}
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(struct {
		Data struct {
			Outcome EvidenceAckStatus `json:"outcome"`
			RunID   string            `json:"run_id"`
		} `json:"data"`
	}{Data: struct {
		Outcome EvidenceAckStatus `json:"outcome"`
		RunID   string            `json:"run_id"`
	}{Outcome: out.Status, RunID: out.Result.RunID.String()}})
}

func validPersistResult(result evidenceoutbox.PersistResult) bool {
	if result.RunID == uuid.Nil || len(result.OutboxIDs) == 0 {
		return false
	}
	for _, id := range result.OutboxIDs {
		if id == uuid.Nil {
			return false
		}
	}
	return true
}

func sameUUIDList(a, b []uuid.UUID) bool {
	if len(a) != len(b) {
		return false
	}
	counts := make(map[uuid.UUID]int, len(a))
	for _, id := range a {
		counts[id]++
	}
	for _, id := range b {
		counts[id]--
		if counts[id] < 0 {
			return false
		}
	}
	for _, count := range counts {
		if count != 0 {
			return false
		}
	}
	return true
}
