package trace

import (
	"testing"

	ibexch "github.com/Rick1330/ibex-harness/packages/clickhouse"
)

func TestUnit_EffectiveWriter(t *testing.T) {
	t.Parallel()

	concrete := &stubTraceWriter{}
	var nilWriter TraceWriter
	var typedNil *stubTraceWriter

	tests := []struct {
		name string
		in   TraceWriter
		want TraceWriter
	}{
		{name: "nil interface", in: nilWriter, want: nil},
		{name: "typed nil", in: typedNil, want: nil},
		{name: "concrete", in: concrete, want: concrete},
	}
	for _, tc := range tests {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			got := EffectiveWriter(tc.in)
			if got != tc.want {
				t.Fatalf("EffectiveWriter() = %v want %v", got, tc.want)
			}
		})
	}
}

type stubTraceWriter struct{}

func (*stubTraceWriter) Write(_ ibexch.TraceRecord) error { return nil }
