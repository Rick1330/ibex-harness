package metrics

// QueryObserver records database query duration. Implemented by AuthRegistry.
type QueryObserver interface {
	ObserveDBQuery(operation DBOperation, seconds float64)
}

// NopQueryObserver discards DB query observations (tests).
type NopQueryObserver struct{}

func (NopQueryObserver) ObserveDBQuery(DBOperation, float64) {}
