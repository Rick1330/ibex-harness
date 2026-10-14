package session

import (
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
