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

// Flush implements http.Flusher for SSE streaming through middleware wrappers.
func (r *statusRecorder) Flush() {
	if f, ok := r.ResponseWriter.(http.Flusher); ok {
		f.Flush()
	}
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

			reg.ObserveHTTPRequest(HTTPRequestObservation{
				Route:      routeTemplate(r),
				Method:     r.Method,
				StatusCode: strconv.Itoa(rec.status),
				Seconds:    time.Since(start).Seconds(),
			})
		})
	}
}

// AuthHTTPMiddleware records auth HTTP request metrics.
func AuthHTTPMiddleware(reg *AuthRegistry) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			start := time.Now()
			rec := &statusRecorder{ResponseWriter: w, status: http.StatusOK}
			next.ServeHTTP(rec, r)

			reg.ObserveHTTPRequest(HTTPRequestObservation{
				Route:      routeTemplate(r),
				Method:     r.Method,
				StatusCode: strconv.Itoa(rec.status),
				Seconds:    time.Since(start).Seconds(),
			})
		})
	}
}
