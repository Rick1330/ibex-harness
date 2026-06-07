package metrics

import (
	"database/sql"

	"github.com/prometheus/client_golang/prometheus"
)

type dbPoolCollector struct {
	gauge *prometheus.GaugeVec
	db    *sql.DB
}

func newDBPoolCollector(db *sql.DB) *dbPoolCollector {
	return &dbPoolCollector{
		gauge: prometheus.NewGaugeVec(prometheus.GaugeOpts{
			Name: "ibex_db_pool_open_connections",
			Help: "Database connection pool open connections by state.",
		}, []string{"state"}),
		db: db,
	}
}

func (c *dbPoolCollector) Describe(ch chan<- *prometheus.Desc) {
	c.gauge.Describe(ch)
}

func (c *dbPoolCollector) Collect(ch chan<- prometheus.Metric) {
	stats := c.db.Stats()
	c.gauge.WithLabelValues("in_use").Set(float64(stats.InUse))
	c.gauge.WithLabelValues("idle").Set(float64(stats.Idle))
	c.gauge.Collect(ch)
}
