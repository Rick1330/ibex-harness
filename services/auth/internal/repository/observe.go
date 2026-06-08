package repository

import (
	"time"

	"github.com/Rick1330/ibex-harness/packages/metrics"
)

func observeQuery(obs metrics.QueryObserver, operation metrics.DBOperation, start time.Time) {
	if obs == nil {
		return
	}
	obs.ObserveDBQuery(metrics.DBQueryObservation{
		Operation: operation,
		Seconds:   time.Since(start).Seconds(),
	})
}
