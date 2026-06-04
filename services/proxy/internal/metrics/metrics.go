package metrics

import (
	"net/http"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"
)

var durationBuckets = []float64{0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5}

type Metrics struct {
	mu       sync.Mutex
	requests map[labelKey]uint64
	buckets  map[labelKey][]uint64
	sums     map[labelKey]float64

	authValidateTotal   map[string]uint64
	authValidateBuckets map[string][]uint64
	authValidateSums    map[string]float64
}

type labelKey struct {
	Method string
	Path   string
	Status string
}

func New() *Metrics {
	return &Metrics{
		requests:            make(map[labelKey]uint64),
		buckets:             make(map[labelKey][]uint64),
		sums:                make(map[labelKey]float64),
		authValidateTotal:   make(map[string]uint64),
		authValidateBuckets: make(map[string][]uint64),
		authValidateSums:    make(map[string]float64),
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
	_, _ = w.Write([]byte(m.renderPrometheus()))
}

func (m *Metrics) renderPrometheus() string {
	m.mu.Lock()
	reqSnap := make(map[labelKey]uint64, len(m.requests))
	for k, v := range m.requests {
		reqSnap[k] = v
	}
	bucketsSnap := make(map[labelKey][]uint64, len(m.buckets))
	for k, v := range m.buckets {
		a := make([]uint64, len(v))
		copy(a, v)
		bucketsSnap[k] = a
	}
	sumsSnap := make(map[labelKey]float64, len(m.sums))
	for k, v := range m.sums {
		sumsSnap[k] = v
	}
	authTotalSnap := make(map[string]uint64, len(m.authValidateTotal))
	for k, v := range m.authValidateTotal {
		authTotalSnap[k] = v
	}
	authBucketsSnap := make(map[string][]uint64, len(m.authValidateBuckets))
	for k, v := range m.authValidateBuckets {
		a := make([]uint64, len(v))
		copy(a, v)
		authBucketsSnap[k] = a
	}
	authSumsSnap := make(map[string]float64, len(m.authValidateSums))
	for k, v := range m.authValidateSums {
		authSumsSnap[k] = v
	}
	m.mu.Unlock()

	var b strings.Builder
	b.WriteString("# HELP ibex_http_requests_total Total HTTP requests.\n")
	b.WriteString("# TYPE ibex_http_requests_total counter\n")
	for _, key := range sortedKeys(reqSnap) {
		writeCounterLine(&b, "ibex_http_requests_total", key, reqSnap[key])
	}

	b.WriteString("# HELP ibex_http_request_duration_seconds HTTP request duration.\n")
	b.WriteString("# TYPE ibex_http_request_duration_seconds histogram\n")
	for _, key := range sortedKeys(bucketsSnap) {
		writeHistogramLines(&b, "ibex_http_request_duration_seconds", key, bucketsSnap[key], sumsSnap[key], durationBuckets)
	}

	b.WriteString("# HELP ibex_proxy_auth_validate_total Auth middleware ValidateToken attempts.\n")
	b.WriteString("# TYPE ibex_proxy_auth_validate_total counter\n")
	for _, result := range sortedAuthResults(authTotalSnap) {
		b.WriteString("ibex_proxy_auth_validate_total{result=")
		writeQuoted(&b, result)
		b.WriteString("} ")
		b.WriteString(strconv.FormatUint(authTotalSnap[result], 10))
		b.WriteString("\n")
	}

	b.WriteString("# HELP ibex_proxy_auth_validate_duration_seconds Auth middleware validate latency.\n")
	b.WriteString("# TYPE ibex_proxy_auth_validate_duration_seconds histogram\n")
	for _, result := range sortedAuthResultsFromBuckets(authBucketsSnap) {
		writeAuthHistogramLines(&b, "ibex_proxy_auth_validate_duration_seconds", result, authBucketsSnap[result], authSumsSnap[result], durationBuckets)
	}

	return b.String()
}

func writeCounterLine(b *strings.Builder, name string, key labelKey, value uint64) {
	b.WriteString(name)
	b.WriteString("{method=")
	writeQuoted(b, key.Method)
	b.WriteString(",path=")
	writeQuoted(b, key.Path)
	b.WriteString(",status=")
	writeQuoted(b, key.Status)
	b.WriteString("} ")
	b.WriteString(strconv.FormatUint(value, 10))
	b.WriteString("\n")
}

func writeHistogramLines(b *strings.Builder, name string, key labelKey, counts []uint64, sum float64, buckets []float64) {
	var cumulative uint64
	for i, bucket := range buckets {
		cumulative += counts[i]
		writeHistogramBucket(b, name+"_bucket", key, strconv.FormatFloat(bucket, 'f', -1, 64), cumulative)
	}
	cumulative += counts[len(buckets)]
	writeHistogramBucket(b, name+"_bucket", key, "+Inf", cumulative)
	writeHistogramValue(b, name+"_sum", key, strconv.FormatFloat(sum, 'f', -1, 64))
	writeHistogramValue(b, name+"_count", key, strconv.FormatUint(cumulative, 10))
}

func writeHistogramBucket(b *strings.Builder, name string, key labelKey, le string, value uint64) {
	b.WriteString(name)
	b.WriteString("{method=")
	writeQuoted(b, key.Method)
	b.WriteString(",path=")
	writeQuoted(b, key.Path)
	b.WriteString(",status=")
	writeQuoted(b, key.Status)
	b.WriteString(",le=")
	writeQuoted(b, le)
	b.WriteString("} ")
	b.WriteString(strconv.FormatUint(value, 10))
	b.WriteString("\n")
}

func writeHistogramValue(b *strings.Builder, name string, key labelKey, value string) {
	b.WriteString(name)
	b.WriteString("{method=")
	writeQuoted(b, key.Method)
	b.WriteString(",path=")
	writeQuoted(b, key.Path)
	b.WriteString(",status=")
	writeQuoted(b, key.Status)
	b.WriteString("} ")
	b.WriteString(value)
	b.WriteString("\n")
}

func writeQuoted(b *strings.Builder, s string) {
	b.WriteByte('"')
	for i := 0; i < len(s); i++ {
		c := s[i]
		if c == '"' || c == '\\' {
			b.WriteByte('\\')
		}
		b.WriteByte(c)
	}
	b.WriteByte('"')
}

func recordHistogram(counts []uint64, buckets []float64, seconds float64) {
	for i, bucket := range buckets {
		if seconds <= bucket {
			counts[i]++
			return
		}
	}
	counts[len(buckets)]++
}

func (m *Metrics) observe(method, path string, status int, seconds float64) {
	key := labelKey{Method: method, Path: path, Status: strconv.Itoa(status)}

	m.mu.Lock()
	defer m.mu.Unlock()

	m.requests[key]++
	if _, ok := m.buckets[key]; !ok {
		m.buckets[key] = make([]uint64, len(durationBuckets)+1)
	}
	recordHistogram(m.buckets[key], durationBuckets, seconds)
	m.sums[key] += seconds
}

// ObserveAuthValidate records auth middleware validation latency and result.
// result must be one of: ok, unauthenticated, error.
func (m *Metrics) ObserveAuthValidate(seconds float64, result string) {
	m.mu.Lock()
	defer m.mu.Unlock()

	m.authValidateTotal[result]++
	if _, ok := m.authValidateBuckets[result]; !ok {
		m.authValidateBuckets[result] = make([]uint64, len(durationBuckets)+1)
	}
	recordHistogram(m.authValidateBuckets[result], durationBuckets, seconds)
	m.authValidateSums[result] += seconds
}

func writeAuthHistogramLines(b *strings.Builder, name, result string, counts []uint64, sum float64, buckets []float64) {
	var cumulative uint64
	for i, bucket := range buckets {
		cumulative += counts[i]
		b.WriteString(name)
		b.WriteString("_bucket{result=")
		writeQuoted(b, result)
		b.WriteString(",le=")
		writeQuoted(b, strconv.FormatFloat(bucket, 'f', -1, 64))
		b.WriteString("} ")
		b.WriteString(strconv.FormatUint(cumulative, 10))
		b.WriteString("\n")
	}
	cumulative += counts[len(buckets)]
	b.WriteString(name)
	b.WriteString("_bucket{result=")
	writeQuoted(b, result)
	b.WriteString(",le=")
	writeQuoted(b, "+Inf")
	b.WriteString("} ")
	b.WriteString(strconv.FormatUint(cumulative, 10))
	b.WriteString("\n")
	b.WriteString(name)
	b.WriteString("_sum{result=")
	writeQuoted(b, result)
	b.WriteString("} ")
	b.WriteString(strconv.FormatFloat(sum, 'f', -1, 64))
	b.WriteString("\n")
	b.WriteString(name)
	b.WriteString("_count{result=")
	writeQuoted(b, result)
	b.WriteString("} ")
	b.WriteString(strconv.FormatUint(cumulative, 10))
	b.WriteString("\n")
}

func sortedAuthResults(m map[string]uint64) []string {
	keys := make([]string, 0, len(m))
	for k := range m {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	return keys
}

func sortedAuthResultsFromBuckets(m map[string][]uint64) []string {
	keys := make([]string, 0, len(m))
	for k := range m {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	return keys
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
