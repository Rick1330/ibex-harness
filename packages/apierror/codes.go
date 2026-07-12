// Package apierror defines canonical IBEX HTTP and gRPC error codes.
package apierror

// Code is a canonical IBEX error code string (UPPER_SNAKE_CASE, stable across API versions).
type Code string

// Client error codes (4xx).
const (
	// CodeMissingToken tells clients to supply an Authorization header before retrying.
	CodeMissingToken Code = "MISSING_TOKEN"
	// CodeInvalidToken tells clients the bearer token is malformed, expired, or revoked.
	CodeInvalidToken Code = "INVALID_TOKEN"
	// CodeInsufficientPermissions tells clients the token lacks scope for this route or org.
	CodeInsufficientPermissions Code = "INSUFFICIENT_PERMISSIONS"
	// CodeInvalidJSON tells clients the request body is not valid JSON.
	CodeInvalidJSON Code = "INVALID_JSON"
	// CodeInvalidRequest tells clients a generic request field failed validation.
	CodeInvalidRequest Code = "INVALID_REQUEST"
	// CodeProviderNotConfigured tells clients no LLM provider is wired for the requested model yet.
	CodeProviderNotConfigured Code = "PROVIDER_NOT_CONFIGURED"
	// CodePayloadTooLarge tells clients to reduce the request body size and retry.
	CodePayloadTooLarge Code = "PAYLOAD_TOO_LARGE"
	// CodeUnsupportedMediaType tells clients to send application/json for JSON endpoints.
	CodeUnsupportedMediaType Code = "UNSUPPORTED_MEDIA_TYPE"
	// CodeValidationError tells clients one or more fields failed semantic validation (see field_errors).
	CodeValidationError Code = "VALIDATION_ERROR"
	// CodeMethodNotAllowed tells clients to use the HTTP method documented for the route.
	CodeMethodNotAllowed Code = "METHOD_NOT_ALLOWED"
	// CodeMissingAgentID tells clients to set X-IBEX-Agent-ID on protected proxy routes.
	CodeMissingAgentID Code = "MISSING_AGENT_ID"
	// CodeAgentNotAuthorized tells clients the agent is unknown or belongs to another org.
	CodeAgentNotAuthorized Code = "AGENT_NOT_AUTHORIZED"
	// CodeAgentSuspended tells clients the agent exists but is paused, suspended, or archived.
	CodeAgentSuspended Code = "AGENT_SUSPENDED"
	// CodeRateLimited tells clients to back off and retry after the rate-limit window.
	CodeRateLimited Code = "RATE_LIMITED"
)

// Server / dependency error codes (5xx).
const (
	// CodeInternalError tells clients an unexpected server fault occurred; retry with backoff.
	CodeInternalError Code = "INTERNAL_ERROR"
	// CodeServiceDegraded tells clients an internal dependency failed unexpectedly (HTTP 5xx).
	CodeServiceDegraded Code = "SERVICE_DEGRADED"
	// CodeAuthUnavailable tells clients the auth service is unreachable; retry later.
	CodeAuthUnavailable Code = "AUTH_UNAVAILABLE"
	// CodeProviderUnavailable tells clients the upstream LLM provider is unreachable or errored.
	CodeProviderUnavailable Code = "PROVIDER_UNAVAILABLE"
	// CodeProviderTimeout tells clients the upstream LLM provider exceeded its deadline.
	CodeProviderTimeout Code = "PROVIDER_TIMEOUT"
)
