package metrics

// HTTPRequestObservation labels proxy/auth HTTP request metrics.
type HTTPRequestObservation struct {
	Route      string
	Method     string
	StatusCode string
	Seconds    float64
}
