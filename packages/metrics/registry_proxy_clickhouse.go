package metrics

import "github.com/prometheus/client_golang/prometheus"

func (r *ProxyRegistry) initClickHouseMetrics() {
	r.clickhouseFlushTotal = prometheus.NewCounterVec(prometheus.CounterOpts{
		Name: "ibex_clickhouse_flush_total",
		Help: "ClickHouse batch flush outcomes.",
	}, []string{"result"})
	r.clickhouseFlushRows = prometheus.NewCounter(prometheus.CounterOpts{
		Name: "ibex_clickhouse_flush_rows_total",
		Help: "Rows included in ClickHouse flush attempts.",
	})
	r.clickhouseDroppedRows = prometheus.NewCounter(prometheus.CounterOpts{
		Name: "ibex_clickhouse_dropped_rows_total",
		Help: "Trace rows dropped because the writer buffer was full.",
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

// IncClickHouseFlush records a flush outcome. Unknown results are recorded as "error".
func (r *ProxyRegistry) IncClickHouseFlush(result string) {
	if result != "ok" && result != "error" {
		result = "error"
	}
	r.clickhouseFlushTotal.WithLabelValues(result).Inc()
}

// AddClickHouseFlushRows adds rows counted in a flush attempt. Non-positive n is ignored.
func (r *ProxyRegistry) AddClickHouseFlushRows(n int) {
	if n > 0 {
		r.clickhouseFlushRows.Add(float64(n))
	}
}

// AddClickHouseDroppedRows records rows dropped when the buffer exceeded MaxBufferSize.
// Non-positive n is ignored.
func (r *ProxyRegistry) AddClickHouseDroppedRows(n int) {
	if n > 0 {
		r.clickhouseDroppedRows.Add(float64(n))
	}
}

// ObserveClickHouseFlushSeconds records flush wall time in elapsed seconds.
func (r *ProxyRegistry) ObserveClickHouseFlushSeconds(seconds float64) {
	r.clickhouseFlushSec.Observe(seconds)
}
