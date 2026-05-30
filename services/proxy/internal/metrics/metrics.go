package metrics

import (
	"fmt"
	"net/http"
	"sort"
	"strconv"
	"sync"
	"time"
)

var durationBuckets = []float64{0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5}

type Metrics struct {
	mu        sync.Mutex
	requests map[labelKey]uint64
	buckets  map[labelKey][]uint64
	sums     map[labelKey]float64
}

type labelKey struct {
	Method string
	Path   string
	Status string
}

func New() *Metrics {
	return &Metrics{
		requests: make(map[labelKey]uint64),
		buckets:  make(map[labelKey][]uint64),
		sums:     make(map[labelKey]float64),
	}
}

func (m *Metrics) Middleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		rec := &statusRecorder{ResponseWriter: w, status: http.StatusOK}
		next.ServeHTTP(rec, r)
		m.observe(r.Method, r.URL.Path, rec.status, time.Since(start).Seconds())
	})
}

func (m *Metrics) ServeHTTP(w http.ResponseWriter, _ *http.Request) {
	w.Header().Set("Content-Type", "text/plain; version=0.0.4; charset=utf-8")

	m.mu.Lock()
	defer m.mu.Unlock()

	fmt.Fprintln(w, "# HELP ibex_http_requests_total Total HTTP requests.")
	fmt.Fprintln(w, "# TYPE ibex_http_requests_total counter")
	for _, key := range sortedKeys(m.requests) {
		fmt.Fprintf(w, "ibex_http_requests_total{method=%q,path=%q,status=%q} %d\n", key.Method, key.Path, key.Status, m.requests[key])
	}

	fmt.Fprintln(w, "# HELP ibex_http_request_duration_seconds HTTP request duration.")
	fmt.Fprintln(w, "# TYPE ibex_http_request_duration_seconds histogram")
	for _, key := range sortedKeys(m.buckets) {
		var cumulative uint64
		for i, bucket := range durationBuckets {
			cumulative += m.buckets[key][i]
			fmt.Fprintf(w, "ibex_http_request_duration_seconds_bucket{method=%q,path=%q,status=%q,le=%q} %d\n", key.Method, key.Path, key.Status, strconv.FormatFloat(bucket, 'f', -1, 64), cumulative)
		}
		cumulative += m.buckets[key][len(durationBuckets)]
		fmt.Fprintf(w, "ibex_http_request_duration_seconds_bucket{method=%q,path=%q,status=%q,le=%q} %d\n", key.Method, key.Path, key.Status, "+Inf", cumulative)
		fmt.Fprintf(w, "ibex_http_request_duration_seconds_sum{method=%q,path=%q,status=%q} %f\n", key.Method, key.Path, key.Status, m.sums[key])
		fmt.Fprintf(w, "ibex_http_request_duration_seconds_count{method=%q,path=%q,status=%q} %d\n", key.Method, key.Path, key.Status, cumulative)
	}
}

func (m *Metrics) observe(method, path string, status int, seconds float64) {
	key := labelKey{Method: method, Path: path, Status: strconv.Itoa(status)}

	m.mu.Lock()
	defer m.mu.Unlock()

	m.requests[key]++
	if _, ok := m.buckets[key]; !ok {
		m.buckets[key] = make([]uint64, len(durationBuckets)+1)
	}
	recorded := false
	for i, bucket := range durationBuckets {
		if seconds <= bucket {
			m.buckets[key][i]++
			recorded = true
			break
		}
	}
	if !recorded {
		m.buckets[key][len(durationBuckets)]++
	}
	m.sums[key] += seconds
}

type statusRecorder struct {
	http.ResponseWriter
	status int
}

func (r *statusRecorder) WriteHeader(status int) {
	r.status = status
	r.ResponseWriter.WriteHeader(status)
}

func sortedKeys[V any](m map[labelKey]V) []labelKey {
	keys := make([]labelKey, 0, len(m))
	for key := range m {
		keys = append(keys, key)
	}
	sort.Slice(keys, func(i, j int) bool {
		if keys[i].Path != keys[j].Path {
			return keys[i].Path < keys[j].Path
		}
		if keys[i].Method != keys[j].Method {
			return keys[i].Method < keys[j].Method
		}
		return keys[i].Status < keys[j].Status
	})
	return keys
}
