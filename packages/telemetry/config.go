// Package telemetry initialises OpenTelemetry providers for IBEX services.
package telemetry

// Config holds OTel provider configuration loaded from environment variables.
type Config struct {
	ServiceName    string
	ServiceVersion string
	Environment    string
	OTLPEndpoint   string
	SampleRatio    float64
}
