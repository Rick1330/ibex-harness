package session

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"

	apierror "github.com/Rick1330/ibex-harness/packages/apierror"
	"github.com/Rick1330/ibex-harness/packages/evidenceoutbox"
	"github.com/google/uuid"
)

func TestWriteEvidenceAck_GoldenHTTPOutcomes(t *testing.T) {
	agentID, sessionID := uuid.New(), uuid.New()
	in := evidenceoutbox.RunInput{
		OrgID: uuid.New(), AgentID: &agentID, SessionID: &sessionID,
		RequestID: "req-golden", TraceID: "aabbccddeeff00112233445566778899",
	}
	runID, outboxID := uuid.New(), uuid.New()
	proof := &evidenceoutbox.ReconciliationProof{
		OrgID: in.OrgID, AgentID: &agentID, SessionID: &sessionID,
		RequestID: in.RequestID, TraceID: in.TraceID, RunID: runID,
		OutboxIDs: []uuid.UUID{outboxID}, RetryableOutboxIDs: []uuid.UUID{outboxID},
	}
	valid := evidenceoutbox.PersistResult{RunID: runID, OutboxIDs: []uuid.UUID{outboxID}}
	cases := []struct {
		name          string
		out           EvidencePersistOutcome
		wantStatus    int
		wantOutcome   EvidenceAckStatus
		wantErrorCode apierror.Code
		wantRunID     string
	}{
		{name: "durable", out: EvidencePersistOutcome{Status: EvidenceAckDurable, Input: in, Result: valid}, wantStatus: http.StatusOK, wantOutcome: EvidenceAckDurable, wantRunID: runID.String()},
		{name: "replayed", out: EvidencePersistOutcome{Status: EvidenceAckReplay, Input: in, Result: evidenceoutbox.PersistResult{RunID: runID, OutboxIDs: []uuid.UUID{outboxID}, Replayed: true}}, wantStatus: http.StatusOK, wantOutcome: EvidenceAckReplay, wantRunID: runID.String()},
		{name: "uncertified-with-durable-proof", out: EvidencePersistOutcome{Status: EvidenceAckUncertified, Input: in, Result: evidenceoutbox.PersistResult{RunID: runID, OutboxIDs: []uuid.UUID{outboxID}}, Proof: proof}, wantStatus: http.StatusAccepted, wantOutcome: EvidenceAckUncertified, wantRunID: runID.String()},
		{name: "uncertified-without-proof", out: EvidencePersistOutcome{Status: EvidenceAckUncertified, Input: in, Result: valid}, wantStatus: http.StatusServiceUnavailable, wantErrorCode: apierror.CodeEvidenceUnavailable},
		{name: "unknown", out: EvidencePersistOutcome{Status: EvidenceAckUnknown, Input: in, Err: errors.New("unknown")}, wantStatus: http.StatusServiceUnavailable, wantErrorCode: apierror.CodeEvidenceUnavailable},
		{name: "failed-or-unavailable", out: EvidencePersistOutcome{Status: EvidenceAckUnavailable, Input: in, Err: errors.New("unavailable")}, wantStatus: http.StatusServiceUnavailable, wantErrorCode: apierror.CodeEvidenceUnavailable},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			response := httptest.NewRecorder()
			WriteEvidenceAck(response, tc.out, in.RequestID)
			if response.Code != tc.wantStatus {
				t.Fatalf("status=%d want %d body=%s", response.Code, tc.wantStatus, response.Body.String())
			}
			if got := response.Header().Get("Content-Type"); got != "application/json" {
				t.Fatalf("content-type=%q", got)
			}
			if tc.wantErrorCode != "" {
				var body apierror.Response
				if err := json.Unmarshal(response.Body.Bytes(), &body); err != nil {
					t.Fatalf("decode error envelope: %v", err)
				}
				if body.Error.Code != tc.wantErrorCode || body.Error.RequestID != in.RequestID || body.Error.Message == "" || body.Error.Timestamp.IsZero() {
					t.Fatalf("unexpected 503 error envelope: %+v", body.Error)
				}
				if body.Error.Detail != "" || body.Error.DocsURL != "" {
					t.Fatalf("503 must not disclose persistence details: %+v", body.Error)
				}
				return
			}
			var body struct {
				Data struct {
					Outcome EvidenceAckStatus `json:"outcome"`
					RunID   string            `json:"run_id"`
				} `json:"data"`
			}
			if err := json.Unmarshal(response.Body.Bytes(), &body); err != nil {
				t.Fatalf("decode success envelope: %v", err)
			}
			if body.Data.Outcome != tc.wantOutcome || body.Data.RunID != tc.wantRunID {
				t.Fatalf("success envelope=%+v want outcome=%q run_id=%q", body.Data, tc.wantOutcome, tc.wantRunID)
			}
		})
	}
}

func TestEvidenceAckHelpers_RejectMalformedResultsAndLists(t *testing.T) {
	validRun, validOutbox := uuid.New(), uuid.New()
	for name, result := range map[string]evidenceoutbox.PersistResult{
		"nil run":       {OutboxIDs: []uuid.UUID{validOutbox}},
		"empty outbox":  {RunID: validRun},
		"nil outbox id": {RunID: validRun, OutboxIDs: []uuid.UUID{uuid.Nil}},
	} {
		if validPersistResult(result) {
			t.Errorf("%s: malformed result accepted", name)
		}
	}
	if !validPersistResult(evidenceoutbox.PersistResult{RunID: validRun, OutboxIDs: []uuid.UUID{validOutbox}}) {
		t.Fatal("valid result rejected")
	}
	other := uuid.New()
	for name, tc := range map[string]struct{ a, b []uuid.UUID }{
		"different lengths":  {a: []uuid.UUID{validOutbox}, b: nil},
		"different values":   {a: []uuid.UUID{validOutbox}, b: []uuid.UUID{other}},
		"duplicate mismatch": {a: []uuid.UUID{validOutbox, validOutbox}, b: []uuid.UUID{validOutbox}},
	} {
		if sameUUIDList(tc.a, tc.b) {
			t.Errorf("%s: mismatched lists considered equal", name)
		}
	}
	if !sameUUIDList([]uuid.UUID{validOutbox, other}, []uuid.UUID{other, validOutbox}) {
		t.Fatal("order-independent matching lists rejected")
	}
}

func TestEvidenceAck_HandlesUnavailableAndUnreconcilablePersisters(t *testing.T) {
	in := evidenceoutbox.RunInput{OrgID: uuid.New(), RequestID: "req", TraceID: "trace"}
	if out := PersistEvidenceForProfile(context.Background(), nil, in, EvidenceAckProfile{}); out.Status != EvidenceAckUnavailable || out.Err == nil {
		t.Fatalf("nil persister outcome=%+v", out)
	}
	plain := plainEvidencePersister{}
	if out := PersistEvidenceForProfile(context.Background(), plain, in, EvidenceAckProfile{}); out.Status != EvidenceAckUnavailable {
		t.Fatalf("unreconcilable persister outcome=%+v", out)
	}
	rowID, runID := uuid.New(), uuid.New()
	agentID, sessionID := uuid.New(), uuid.New()
	in.AgentID, in.SessionID = &agentID, &sessionID
	proof := &evidenceoutbox.ReconciliationProof{OrgID: in.OrgID, AgentID: &agentID, SessionID: &sessionID, RequestID: in.RequestID, TraceID: in.TraceID, RunID: runID, OutboxIDs: []uuid.UUID{rowID}, RetryableOutboxIDs: []uuid.UUID{rowID}}
	store := &fakeEvidenceStore{err: errors.New("db down"), proof: proof}
	if out := PersistEvidenceForProfile(context.Background(), store, in, EvidenceAckProfile{}); out.Status != EvidenceAckUnavailable {
		t.Fatalf("required profile incorrectly accepted uncertified proof: %+v", out)
	}
	if sameUUIDList([]uuid.UUID{rowID, runID}, []uuid.UUID{rowID, rowID}) {
		t.Fatal("unmatched UUID multiset accepted")
	}
}

type plainEvidencePersister struct{}

func (plainEvidencePersister) PersistRun(context.Context, evidenceoutbox.RunInput) (evidenceoutbox.PersistResult, error) {
	return evidenceoutbox.PersistResult{}, errors.New("db down")
}
