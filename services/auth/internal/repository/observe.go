package repository

import (
	"time"

	"github.com/Rick1330/ibex-harness/packages/metrics"
)

func observeQuery(obs metrics.QueryObserver, operation string, start time.Time) {
	if obs == nil {
		return
	}
	obs.ObserveDBQuery(operation, time.Since(start).Seconds())
}
