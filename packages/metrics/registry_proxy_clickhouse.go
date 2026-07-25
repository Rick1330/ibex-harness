package metrics

import "github.com/prometheus/client_golang/prometheus"

func (r *ProxyRegistry) initClickHouseMetrics() {
	r.clickhouseFlushTotal = prometheus.NewCounterVec(prometheus.CounterOpts{
		Name: "ibex_clickhouse_flush_total",
		Help: "ClickHouse batch flush outcomes.",
	}, []string{"result"})
	r.clickhouseFlushRows = prometheus.NewCounter(prometheus.CounterOpts{
		Name: "ibex_clickhouse_flush_rows",
		Help: "Rows included in ClickHouse flush attempts.",
	})
	r.clickhouseFlushSec = prometheus.NewHistogram(prometheus.HistogramOpts{
		Name:    "ibex_clickhouse_flush_duration_seconds",
		Help:    "ClickHouse batch flush duration.",
		Buckets: LatencyBuckets,
	})
	for _, result := range []string{"ok", "error"} {
		r.clickhouseFlushTotal.WithLabelValues(result)
	}
}

// IncClickHouseFlush records a flush outcome (ok|error).
func (r *ProxyRegistry) IncClickHouseFlush(result string) {
	if result != "ok" && result != "error" {
		result = "error"
	}
	r.clickhouseFlushTotal.WithLabelValues(result).Inc()
}

// AddClickHouseFlushRows adds rows counted in a flush attempt.
func (r *ProxyRegistry) AddClickHouseFlushRows(n int) {
	if n > 0 {
		r.clickhouseFlushRows.Add(float64(n))
	}
}

// ObserveClickHouseFlushSeconds records flush wall time.
func (r *ProxyRegistry) ObserveClickHouseFlushSeconds(seconds float64) {
	r.clickhouseFlushSec.Observe(seconds)
}
