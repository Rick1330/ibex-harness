// Package apierror defines canonical IBEX HTTP and gRPC error codes.
package apierror

// Code is a canonical IBEX error code string (UPPER_SNAKE_CASE, stable across API versions).
type Code string

// Client error codes (4xx).
const (
	CodeMissingToken            Code = "MISSING_TOKEN"
	CodeInvalidToken            Code = "INVALID_TOKEN"
	CodeInsufficientPermissions Code = "INSUFFICIENT_PERMISSIONS"
	CodeInvalidJSON             Code = "INVALID_JSON"
	CodeInvalidRequest          Code = "INVALID_REQUEST"
	CodeProviderNotConfigured   Code = "PROVIDER_NOT_CONFIGURED"
	CodePayloadTooLarge         Code = "PAYLOAD_TOO_LARGE"
	CodeUnsupportedMediaType    Code = "UNSUPPORTED_MEDIA_TYPE"
	CodeValidationError         Code = "VALIDATION_ERROR"
	CodeMethodNotAllowed        Code = "METHOD_NOT_ALLOWED"
	CodeMissingAgentID          Code = "MISSING_AGENT_ID"
	CodeAgentNotAuthorized      Code = "AGENT_NOT_AUTHORIZED"
	CodeAgentSuspended          Code = "AGENT_SUSPENDED"
	CodeRateLimited             Code = "RATE_LIMITED"
)

// Server / dependency error codes (5xx).
const (
	CodeInternalError   Code = "INTERNAL_ERROR"
	CodeServiceDegraded Code = "SERVICE_DEGRADED"
	CodeAuthUnavailable Code = "AUTH_UNAVAILABLE"
)
