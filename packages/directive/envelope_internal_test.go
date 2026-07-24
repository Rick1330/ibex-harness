package directive

import (
	"testing"

	"github.com/google/uuid"
)

func TestUnit_MarshalUnmarshalEnvelope(t *testing.T) {
	t.Parallel()
	versionID := uuid.New()
	raw, err := marshalEnvelope(Resolved{
		Content: "hello", InjectionMode: "", VersionID: versionID,
	})
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	got, err := unmarshalEnvelope(raw)
	if err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if got.Content != "hello" || got.InjectionMode != DefaultInjectionMode {
		t.Fatalf("got=%+v", got)
	}
	if got.VersionID != versionID {
		t.Fatalf("version_id=%s", got.VersionID)
	}
}

func TestUnit_UnmarshalEnvelopeErrors(t *testing.T) {
	t.Parallel()
	cases := []struct {
		name string
		raw  string
	}{
		{"invalid json", "{"},
		{"bad version", `{"v":99,"content":"x","injection_mode":"system_first"}`},
		{"bad version_id", `{"v":1,"content":"x","injection_mode":"system_first","version_id":"not-a-uuid"}`},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			if _, err := unmarshalEnvelope([]byte(tc.raw)); err == nil {
				t.Fatal("expected error")
			}
		})
	}
}

func TestUnit_UnmarshalEnvelopeEmptyVersionID(t *testing.T) {
	t.Parallel()
	got, err := unmarshalEnvelope([]byte(`{"v":1,"content":"","injection_mode":""}`))
	if err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if got.HasContent() || got.VersionID != uuid.Nil {
		t.Fatalf("got=%+v", got)
	}
}
