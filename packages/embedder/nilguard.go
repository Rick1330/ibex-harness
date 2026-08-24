package embedder

import "reflect"

func embedderIsMissing(e Embedder) bool {
	if e == nil {
		return true
	}
	v := reflect.ValueOf(e)
	return v.Kind() == reflect.Ptr && v.IsNil()
}
