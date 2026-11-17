package metrics

// QueryObserver records database query duration. Implemented by AuthRegistry.
type QueryObserver interface {
	ObserveDBQuery(obs DBQueryObservation)
}

// NopQueryObserver discards DB query observations (tests).
type NopQueryObserver struct{}

func (NopQueryObserver) ObserveDBQuery(DBQueryObservation) {
	// Deliberately empty: this type exists to satisfy QueryObserver while
	// recording nothing, so a caller can opt out of query metrics without a
	// nil check or a branch on every observation.
}
