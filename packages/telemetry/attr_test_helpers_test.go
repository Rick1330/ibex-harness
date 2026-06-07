package telemetry_test

import (
	"net/http"

	"github.com/Rick1330/ibex-harness/packages/reqid"
	"go.opentelemetry.io/otel/attribute"
)

func reqidMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		id := reqid.New()
		ctx := reqid.WithRequestID(r.Context(), id)
		next.ServeHTTP(w, r.WithContext(ctx))
	})
}

func attrString(attrs []attribute.KeyValue, key string) string {
	v, _ := attrStringOK(attrs, key)
	return v
}

func attrStringOK(attrs []attribute.KeyValue, key string) (string, bool) {
	for _, a := range attrs {
		if string(a.Key) == key {
			return a.Value.AsString(), true
		}
	}
	return "", false
}

func attrInt(attrs []attribute.KeyValue, key string) int64 {
	for _, a := range attrs {
		if string(a.Key) == key {
			return a.Value.AsInt64()
		}
	}
	return 0
}
