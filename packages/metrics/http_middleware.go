package metrics

import (
	"net/http"
	"strconv"
	"time"
)

type statusRecorder struct {
	http.ResponseWriter
	status int
}

func (r *statusRecorder) WriteHeader(status int) {
	r.status = status
	r.ResponseWriter.WriteHeader(status)
}

// HTTPMiddleware records proxy HTTP request metrics and active connections.
func HTTPMiddleware(reg *ProxyRegistry) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			reg.IncActiveConnection()
			defer reg.DecActiveConnection()

			start := time.Now()
			rec := &statusRecorder{ResponseWriter: w, status: http.StatusOK}
			next.ServeHTTP(rec, r)

			reg.ObserveHTTPRequest(
				routeTemplate(r),
				r.Method,
				strconv.Itoa(rec.status),
				time.Since(start).Seconds(),
			)
		})
	}
}
