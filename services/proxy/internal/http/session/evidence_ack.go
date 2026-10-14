package session

import (
	"context"
	"errors"
	"net/http"

	apierror "github.com/Rick1330/ibex-harness/packages/apierror"
	"github.com/Rick1330/ibex-harness/packages/evidenceoutbox"
	"github.com/google/uuid"
)

// EvidenceAckProfile is selected by the operation's capture policy. Required
// operations fail closed when the write cannot be certified; degraded profiles
// return an explicit uncertified result and must not label it durable.
type EvidenceAckProfile struct {
	Required         bool
	AllowUncertified bool
}

// PersistEvidenceForProfile is the acknowledgement boundary for synchronous
// callers. The legacy PersistEvidence function remains telemetry-only and
// fail-open because it runs after a response has already been committed.
func PersistEvidenceForProfile(ctx context.Context, p EvidencePersister, in evidenceoutbox.RunInput, profile EvidenceAckProfile) EvidencePersistOutcome {
	p = EffectiveEvidence(p)
	if p == nil {
		return evidenceAckFailure(profile, errors.New("evidence persister is unavailable"))
	}
	result, err := p.PersistRun(ctx, in)
	if err != nil {
		return evidenceAckFailure(profile, err)
	}
	if result.RunID == uuid.Nil || len(result.OutboxIDs) == 0 {
		return evidenceAckFailure(profile, errors.New("evidence commit outcome is unknown"))
	}
	if result.Replayed {
		return EvidencePersistOutcome{Result: result, Status: EvidenceAckReplay}
	}
	return EvidencePersistOutcome{Result: result, Status: EvidenceAckDurable}
}

func evidenceAckFailure(profile EvidenceAckProfile, err error) EvidencePersistOutcome {
	if profile.Required && !profile.AllowUncertified {
		return EvidencePersistOutcome{Status: EvidenceAckUnavailable, Err: err}
	}
	return EvidencePersistOutcome{Status: EvidenceAckUncertified, Err: err}
}

// EvidenceAckHTTP maps only the acknowledgement state, not the underlying
// database error. The error detail must remain server-side and secret-safe.
func EvidenceAckHTTP(status EvidenceAckStatus) (int, apierror.Code) {
	switch status {
	case EvidenceAckDurable, EvidenceAckReplay, EvidenceAckUncertified:
		return http.StatusOK, ""
	case EvidenceAckUnavailable:
		return http.StatusServiceUnavailable, apierror.CodeServiceDegraded
	default:
		return http.StatusInternalServerError, apierror.CodeInternalError
	}
}
