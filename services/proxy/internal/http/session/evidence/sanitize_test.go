package evidence

import (
	"encoding/json"
	"strings"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/evidenceoutbox"
	"github.com/google/uuid"
)

func TestSanitizeRunInput_AllowlistedFieldsRemainMetadata(t *testing.T) {
	in := validRunInput()
	in.ModelID = "gpt-4o-mini"
	in.TokenUsage = &evidenceoutbox.TokenUsage{InputTokens: 120, OutputTokens: 45, TotalTokens: 165}
	in.RootSpanID = "aabbccddeeff0011"
	in.MetricsSpanID = "1122334455667788"
	in.Spans = []evidenceoutbox.SpanInput{{
		SpanID: "aabbccddeeff0011", OperationKind: "proxy.chat", Status: "ok",
		StartedAt: in.StartedAt, EndedAt: in.EndedAt,
	}}
	in.Metrics = &evidenceoutbox.AssemblyMetrics{TotalMs: 12, CandidatesEvaluated: 2}
	in.Candidates = []evidenceoutbox.ScoreCandidate{{
		MemoryID: uuid.New(), RetrievalRank: 0, Category: "episodic", ScoreSchema: "score.v1",
		Similarity: floatPtr(0.91), ScoreComponents: map[string]float64{"similarity": 0.91}, Exclusion: "included",
	}}
	deltaRank := -1
	in.Candidates[0].DeltaRank = &deltaRank
	filterCandidate := in.Candidates[0]
	filterCandidate.MemoryID = uuid.New()
	filterCandidate.Exclusion = "filter"
	filterCandidate.DeltaRank = nil
	in.Candidates = append(in.Candidates, filterCandidate)
	in.Directive = &evidenceoutbox.DirectiveSnapshot{DirectiveVersionID: uuidPtr(uuid.New()), ContentHash: strings.Repeat("a", 64)}

	got := SanitizeRunInput(in)
	if got.Withheld || got.RedactionClass != evidenceoutbox.RedactionClassMetadata {
		t.Fatalf("classification=%q withheld=%v dropped=%v", got.RedactionClass, got.Withheld, got.DroppedFields)
	}
	if got.Input.OrgID != in.OrgID || got.Input.SessionID == nil || *got.Input.SessionID != *in.SessionID {
		t.Fatalf("required identity was not preserved: %+v", got.Input)
	}
	if got.Input.Metrics == nil || got.Input.Candidates[0].MemoryID != in.Candidates[0].MemoryID || got.Input.Candidates[0].Category != "episodic" || got.Input.Directive == nil {
		t.Fatalf("allowlisted typed metadata missing: %+v", got.Input)
	}
	if got.Input.ModelID != in.ModelID || got.Input.TokenUsage == nil || got.Input.TokenUsage.TotalTokens != 165 {
		t.Fatalf("safe model/token metadata missing: model=%q usage=%+v", got.Input.ModelID, got.Input.TokenUsage)
	}
	if len(got.Input.Candidates) != 2 || got.Input.Candidates[0].Exclusion != "included" || got.Input.Candidates[0].DeltaRank == nil || *got.Input.Candidates[0].DeltaRank != -1 || got.Input.Candidates[1].Exclusion != "filter" {
		t.Fatalf("producer candidate metadata changed: %+v", got.Input.Candidates[0])
	}
	if len(got.DroppedFields) != 0 {
		t.Fatalf("unexpected dropped fields: %v", got.DroppedFields)
	}
}

func TestSanitizeRunInput_PayloadLikeAndFreeFormFieldsDowngrade(t *testing.T) {
	in := validRunInput()
	in.ErrorCode = "upstream body: private provider response"
	in.Tools = []evidenceoutbox.ToolAudit{{
		ToolName: "search", SanitizedArgs: map[string]any{"query": "private memory text"},
	}}
	in.SessionEvents = []evidenceoutbox.SessionEventInput{{
		EventType: "inference_response", Data: map[string]any{"content": "secret message body"},
	}}
	in.Spans = []evidenceoutbox.SpanInput{{
		SpanID: "aabbccddeeff0011", OperationKind: "proxy.chat", Status: "error",
		ErrorCode: "raw upstream error body", Attributes: map[string]any{"prompt": "sensitive prompt"},
	}}
	in.Candidates = []evidenceoutbox.ScoreCandidate{{
		MemoryID: uuid.New(), RetrievalRank: 1, Category: "raw memory item text",
	}}

	got := SanitizeRunInput(in)
	if got.Withheld || got.RedactionClass != evidenceoutbox.RedactionClassRedacted {
		t.Fatalf("classification=%q withheld=%v dropped=%v", got.RedactionClass, got.Withheld, got.DroppedFields)
	}
	if got.Input.RedactionClass != evidenceoutbox.RedactionClassRedacted || got.Input.Producer == nil || got.Input.Producer.RedactionClass != evidenceoutbox.RedactionClassRedacted {
		t.Fatalf("redacted classification was not bound into the sanitized proof: row=%q producer=%+v", got.Input.RedactionClass, got.Input.Producer)
	}
	if got.Input.ErrorCode != "" || len(got.Input.Tools) != 0 || len(got.Input.SessionEvents) != 0 {
		t.Fatalf("payload-like fields survived sanitization: %+v", got.Input)
	}
	if len(got.Input.Spans) != 1 || got.Input.Spans[0].ErrorCode != "" || len(got.Input.Spans[0].Attributes) != 0 {
		t.Fatalf("unsafe span fields survived sanitization: %+v", got.Input.Spans)
	}
	if got.Input.Candidates[0].Category != "" || got.Input.Completeness != "redacted" {
		t.Fatalf("unsafe candidate or completeness state: %+v", got.Input)
	}
	raw, err := json.Marshal(got.Input)
	if err != nil {
		t.Fatal(err)
	}
	for _, forbidden := range []string{"private provider response", "private memory text", "secret message body", "sensitive prompt", "raw memory item text"} {
		if strings.Contains(string(raw), forbidden) {
			t.Fatalf("sanitized output contains %q: %s", forbidden, raw)
		}
	}
}

func TestSanitizeRunInput_UnknownFieldsAndInvalidAllowlistedValuesDowngrade(t *testing.T) {
	in := validRunInput()
	in.CaptureMode = "metadata but includes content"
	in.RootSpanID = "not-a-span-id"
	in.DeployImageDigest = "arbitrary-build-string"
	in.ModelID = "provider response with content\n"
	in.TokenUsage = &evidenceoutbox.TokenUsage{InputTokens: 12, OutputTokens: 8, TotalTokens: 1}
	in.Candidates = []evidenceoutbox.ScoreCandidate{{
		MemoryID: uuid.New(), RetrievalRank: 1, ScoreComponents: map[string]float64{"free_form": 0.3},
	}}

	got := SanitizeRunInput(in)
	if got.RedactionClass != evidenceoutbox.RedactionClassRedacted {
		t.Fatalf("classification=%q dropped=%v", got.RedactionClass, got.DroppedFields)
	}
	if got.Input.CaptureMode != "" || got.Input.RootSpanID != "" || got.Input.DeployImageDigest != "" || got.Input.ModelID != "" || got.Input.TokenUsage != nil {
		t.Fatalf("invalid values were not stripped: %+v", got.Input)
	}
	if len(got.Input.Candidates[0].ScoreComponents) != 0 {
		t.Fatalf("unknown score component survived: %+v", got.Input.Candidates[0].ScoreComponents)
	}
}

func TestSanitizeRunInput_EmptyAndPartialRowsAreWithheld(t *testing.T) {
	for name, in := range map[string]evidenceoutbox.RunInput{
		"empty":         {},
		"missing trace": {OrgID: uuid.New(), AgentID: uuidPtr(uuid.New()), SessionID: uuidPtr(uuid.New()), RequestID: "req-1"},
	} {
		t.Run(name, func(t *testing.T) {
			got := SanitizeRunInput(in)
			if !got.Withheld || got.RedactionClass != evidenceoutbox.RedactionClassRedacted || got.Input.OrgID != uuid.Nil {
				t.Fatalf("empty/partial identity was emitted: %+v", got)
			}
		})
	}
	missingFence := validRunInput()
	missingFence.TombstoneFence = nil
	if got := SanitizeRunInput(missingFence); !got.Withheld {
		t.Fatalf("row without authoritative fence must be withheld: %+v", got)
	}
}

func TestSanitizeRunInput_MinimalCompleteIdentityIsMetadata(t *testing.T) {
	in := validRunInput()
	in.StartedAt = time.Time{}
	in.EndedAt = time.Time{}
	got := SanitizeRunInput(in)
	if got.Withheld || got.RedactionClass != evidenceoutbox.RedactionClassMetadata {
		t.Fatalf("minimal valid row classification=%q withheld=%v dropped=%v", got.RedactionClass, got.Withheld, got.DroppedFields)
	}
}

func TestSanitizeRunInput_DoesNotUpgradePreRedactedInput(t *testing.T) {
	in := validRunInput()
	in.RedactionClass = evidenceoutbox.RedactionClassRedacted
	in.Producer.RedactionClass = evidenceoutbox.RedactionClassRedacted
	got := SanitizeRunInput(in)
	if got.Withheld || got.RedactionClass != evidenceoutbox.RedactionClassRedacted || got.Input.RedactionClass != evidenceoutbox.RedactionClassRedacted {
		t.Fatalf("pre-redacted input was upgraded: %+v", got)
	}
}

func validRunInput() evidenceoutbox.RunInput {
	agentID := uuid.New()
	sessionID := uuid.New()
	now := time.Date(2026, 10, 14, 12, 0, 0, 0, time.UTC)
	const fenceVersion = int64(1)
	producer := &evidenceoutbox.ProducerMetadata{
		RedactionClass: evidenceoutbox.RedactionClassMetadata, RedactionProofVersion: RedactionProofVersion,
		ResourceType: "session", ResourceID: sessionID.String(), ResourceVersion: fenceVersion,
		Source: "proxy.session.evidence",
	}
	return evidenceoutbox.RunInput{
		OrgID: uuid.New(), AgentID: &agentID, SessionID: &sessionID,
		RequestID: "req-20261014-1", TraceID: "aabbccddeeff00112233445566778899",
		Status: "ok", Completeness: "complete", StartedAt: now, EndedAt: now.Add(time.Second),
		RedactionClass: evidenceoutbox.RedactionClassMetadata, Producer: producer,
		TombstoneFence: &evidenceoutbox.TombstoneFence{ResourceType: "session", ResourceID: sessionID.String(), ResourceVersion: fenceVersion},
	}
}

func uuidPtr(value uuid.UUID) *uuid.UUID { return &value }
func floatPtr(value float64) *float64    { return &value }
