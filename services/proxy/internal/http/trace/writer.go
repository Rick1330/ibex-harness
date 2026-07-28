package trace

import (
	"reflect"

	ibexch "github.com/Rick1330/ibex-harness/packages/clickhouse"
)

// TraceWriter decouples HTTP trace emit from the ClickHouse writer so handlers
// and tests can inject a narrow Write contract without importing storage details.
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
