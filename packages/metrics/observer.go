package metrics

// QueryObserver records database query duration. Implemented by AuthRegistry.
type QueryObserver interface {
	ObserveDBQuery(obs DBQueryObservation)
}

// NopQueryObserver discards DB query observations (tests).
type NopQueryObserver struct{}

func (NopQueryObserver) ObserveDBQuery(DBQueryObservation) {}
