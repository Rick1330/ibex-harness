package trace

import (
	"testing"

	ibexch "github.com/Rick1330/ibex-harness/packages/clickhouse"
)

func TestUnit_EffectiveWriter(t *testing.T) {
	t.Parallel()

	var nilWriter TraceWriter
	if EffectiveWriter(nilWriter) != nil {
		t.Fatal("expected nil interface to stay nil")
	}

	var typedNil *stubTraceWriter
	if EffectiveWriter(typedNil) != nil {
		t.Fatal("expected typed nil to become nil")
	}

	w := &stubTraceWriter{}
	if EffectiveWriter(w) != w {
		t.Fatal("expected concrete writer passthrough")
	}
}

type stubTraceWriter struct{}

func (*stubTraceWriter) Write(_ ibexch.TraceRecord) error { return nil }
