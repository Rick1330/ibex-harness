package healthcheck

import "context"

// Checker is a named dependency probe. Returns nil when healthy.
type Checker func(ctx context.Context) error

// Response is the JSON body for /health and /ready.
type Response struct {
	Status string           `json:"status"`
	Checks map[string]Check `json:"checks"`
}

// Check is the result of a single dependency probe.
type Check struct {
	Status    string `json:"status"`
	Message   string `json:"message,omitempty"`
	LatencyMs int64  `json:"latency_ms"`
}
