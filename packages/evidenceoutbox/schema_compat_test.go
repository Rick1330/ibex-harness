package evidenceoutbox

import (
	"encoding/json"
	"strings"
	"testing"
)

func TestUnit_SchemaVersionConstant(t *testing.T) {
	t.Parallel()
	if SchemaVersion != "evidence.v1" {
		t.Fatalf("SchemaVersion=%q want evidence.v1", SchemaVersion)
	}
	if ScoreSchemaInterim != "interim_v1" {
		t.Fatalf("ScoreSchemaInterim=%q want interim_v1", ScoreSchemaInterim)
	}
}

func TestUnit_ValidateRunInput(t *testing.T) {
	t.Parallel()
	err := validateRunInput(RunInput{})
	if err == nil {
		t.Fatal("expected org_id error")
	}
}

func TestUnit_ValidateRunInput_Completeness(t *testing.T) {
	t.Parallel()
	base := RunInput{
		OrgID:     mustParseUUID("11111111-1111-1111-1111-111111111111"),
		RequestID: "req",
		TraceID:   "aabbccddeeff00112233445566778899",
	}
	ok := base
	ok.Completeness = "complete"
	if err := validateRunInput(ok); err != nil {
		t.Fatalf("complete: %v", err)
	}
	bad := base
	bad.Completeness = "not-a-real-value"
	if err := validateRunInput(bad); err == nil {
		t.Fatal("expected unsupported completeness error")
	}
}

func TestUnit_ValidateRunInput_W3CIDs(t *testing.T) {
	t.Parallel()
	base := RunInput{
		OrgID:     mustParseUUID("11111111-1111-1111-1111-111111111111"),
		RequestID: "req",
		TraceID:   "aabbccddeeff00112233445566778899",
	}
	if err := validateRunInput(base); err != nil {
		t.Fatalf("valid: %v", err)
	}
	cases := []struct {
		name string
		mut  func(*RunInput)
	}{
		{"malformed_trace", func(in *RunInput) { in.TraceID = "not-hex" }},
		{"all_zero_trace", func(in *RunInput) { in.TraceID = strings.Repeat("0", 32) }},
		{"malformed_span", func(in *RunInput) {
			in.Spans = []SpanInput{{SpanID: "short", OperationKind: "proxy.chat"}}
		}},
		{"all_zero_span", func(in *RunInput) {
			in.Spans = []SpanInput{{SpanID: strings.Repeat("0", 16), OperationKind: "proxy.chat"}}
		}},
		{"malformed_parent", func(in *RunInput) {
			in.Spans = []SpanInput{{
				SpanID: "1111111111111111", ParentSpanID: "bad", OperationKind: "proxy.chat",
			}}
		}},
		{"empty_optional_ok", func(in *RunInput) {
			in.RootSpanID = ""
			in.Spans = []SpanInput{{SpanID: "1111111111111111", OperationKind: "proxy.chat"}}
		}},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			in := base
			tc.mut(&in)
			err := validateRunInput(in)
			if tc.name == "empty_optional_ok" {
				if err != nil {
					t.Fatalf("want nil, got %v", err)
				}
				return
			}
			if err == nil {
				t.Fatal("expected validation error")
			}
		})
	}
}

func TestUnit_OutboxPayloadRoundTripCompatibility(t *testing.T) {
	t.Parallel()
	// Old consumer ignores unknown fields; new producer may add keys.
	legacy := []byte(`{"run_id":"a","request_id":"b","trace_id":"c","schema_version":"evidence.v1"}`)
	var m map[string]any
	if err := json.Unmarshal(legacy, &m); err != nil {
		t.Fatal(err)
	}
	m["completeness"] = "partial"
	m["unknown_future"] = 42
	raw, err := json.Marshal(m)
	if err != nil {
		t.Fatal(err)
	}
	var again map[string]any
	if err := json.Unmarshal(raw, &again); err != nil {
		t.Fatal(err)
	}
	if again["schema_version"] != SchemaVersion {
		t.Fatalf("schema_version=%v", again["schema_version"])
	}
	if _, ok := again["unknown_future"]; !ok {
		t.Fatal("unknown attributes must round-trip")
	}
}

func TestUnit_EnvelopeVersionRejectsBlankTrace(t *testing.T) {
	t.Parallel()
	in := RunInput{
		OrgID:     mustParseUUID("11111111-1111-1111-1111-111111111111"),
		RequestID: "req",
	}
	if err := validateRunInput(in); err == nil {
		t.Fatal("expected trace_id required")
	}
}
