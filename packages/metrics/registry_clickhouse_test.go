package metrics

import (
	"strings"
	"testing"

	dto "github.com/prometheus/client_model/go"
)

func TestUnit_ProxyRegistry_ClickHouseMetrics(t *testing.T) {
	t.Parallel()
	reg := NewProxy("test-proxy-ch")

	reg.IncClickHouseFlush("ok")
	reg.IncClickHouseFlush("error")
	reg.IncClickHouseFlush("weird") // coerced to error
	reg.AddClickHouseFlushRows(3)
	reg.AddClickHouseFlushRows(0)
	reg.AddClickHouseFlushRows(-1)
	reg.AddClickHouseDroppedRows(2)
	reg.AddClickHouseDroppedRows(0)
	reg.ObserveClickHouseFlushSeconds(0.012)

	body := scrapeMetrics(t, reg.Gatherer())
	for _, name := range []string{
		"ibex_clickhouse_flush_total",
		"ibex_clickhouse_flush_rows_total",
		"ibex_clickhouse_dropped_rows_total",
		"ibex_clickhouse_flush_duration_seconds",
	} {
		if !strings.Contains(body, name) {
			t.Fatalf("missing %s in:\n%s", name, body)
		}
	}

	families := gatherFamilies(t, reg.Gatherer())
	flush := families["ibex_clickhouse_flush_total"]
	if flush == nil {
		t.Fatal("missing flush_total family")
	}
	okCount := counterByLabel(flush, "result", "ok")
	errCount := counterByLabel(flush, "result", "error")
	if okCount != 1 {
		t.Fatalf("ok count=%v", okCount)
	}
	if errCount != 2 { // explicit error + coerced weird
		t.Fatalf("error count=%v", errCount)
	}
	if rows := counterValue(families["ibex_clickhouse_flush_rows_total"]); rows != 3 {
		t.Fatalf("rows=%v", rows)
	}
	if dropped := counterValue(families["ibex_clickhouse_dropped_rows_total"]); dropped != 2 {
		t.Fatalf("dropped=%v", dropped)
	}
}

func gatherFamilies(t *testing.T, g interface {
	Gather() ([]*dto.MetricFamily, error)
}) map[string]*dto.MetricFamily {
	t.Helper()
	mfs, err := g.Gather()
	if err != nil {
		t.Fatal(err)
	}
	out := make(map[string]*dto.MetricFamily, len(mfs))
	for _, mf := range mfs {
		out[mf.GetName()] = mf
	}
	return out
}

func counterByLabel(mf *dto.MetricFamily, label, value string) float64 {
	for _, m := range mf.GetMetric() {
		for _, lp := range m.GetLabel() {
			if lp.GetName() == label && lp.GetValue() == value {
				return m.GetCounter().GetValue()
			}
		}
	}
	return 0
}

func counterValue(mf *dto.MetricFamily) float64 {
	if mf == nil || len(mf.GetMetric()) == 0 {
		return 0
	}
	return mf.GetMetric()[0].GetCounter().GetValue()
}
