package trace

import (
	"reflect"

	ibexch "github.com/Rick1330/ibex-harness/packages/clickhouse"
)

// TraceWriter accepts assembled llm_traces rows (implemented by packages/clickhouse.Writer).
type TraceWriter interface {
	Write(record ibexch.TraceRecord) error
}

// EffectiveWriter returns a true-nil interface when w is nil or a typed-nil
// pointer/interface. Boxing nil *T into TraceWriter would otherwise pass != nil
// checks and panic on the first Write.
func EffectiveWriter(w TraceWriter) TraceWriter {
	if w == nil {
		return nil
	}
	v := reflect.ValueOf(w)
	switch v.Kind() {
	case reflect.Pointer, reflect.Interface, reflect.Map, reflect.Slice, reflect.Chan, reflect.Func:
		if v.IsNil() {
			return nil
		}
	}
	return w
}
