package metrics

// HTTPRequestObservation labels proxy/auth HTTP request metrics.
type HTTPRequestObservation struct {
	Route      string
	Method     string
	StatusCode string
	Seconds    float64
}

// StreamObservation labels SSE forward duration metrics.
type StreamObservation struct {
	Provider string
	Status   string
	Seconds  float64
}
