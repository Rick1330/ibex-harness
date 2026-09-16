package evidenceoutbox

import (
	"encoding/json"
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
