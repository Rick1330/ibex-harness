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
	// CodePermissionElevationDenied tells clients the caller tried to grant bits they do not hold.
	CodePermissionElevationDenied Code = "PERMISSION_ELEVATION_DENIED"
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
	// CodeInvalidCredential tells clients a provider API key failed upstream validation.
	CodeInvalidCredential Code = "INVALID_CREDENTIAL"
	// CodeMethodNotAllowed tells clients to use the HTTP method documented for the route.
	CodeMethodNotAllowed Code = "METHOD_NOT_ALLOWED"
	// CodeMissingAgentID tells clients to set X-IBEX-Agent-ID on protected proxy routes.
	CodeMissingAgentID Code = "MISSING_AGENT_ID"
	// CodeAgentNotAuthorized tells clients the agent is unknown or belongs to another org.
	CodeAgentNotAuthorized Code = "AGENT_NOT_AUTHORIZED"
	// CodeAgentSuspended tells clients the agent exists but is paused, suspended, or archived.
	CodeAgentSuspended Code = "AGENT_SUSPENDED"
	// CodeOrgSuspended tells clients the organization is suspended and must not receive traffic.
	CodeOrgSuspended Code = "ORG_SUSPENDED"
	// CodeLastOwnerProtected tells clients the last remaining owner cannot be demoted or removed.
	CodeLastOwnerProtected Code = "LAST_OWNER_PROTECTED"
	// CodeAgentSlugConflict tells clients the agent slug is already taken within the organization.
	CodeAgentSlugConflict Code = "AGENT_SLUG_CONFLICT"
	// CodeAgentHasSessions tells clients the agent cannot be deleted while session history exists.
	CodeAgentHasSessions Code = "AGENT_HAS_SESSIONS"
	// CodeAgentStatusConflict tells clients a concurrent lifecycle transition changed agent status.
	CodeAgentStatusConflict Code = "AGENT_STATUS_CONFLICT"
	// CodeRateLimited tells clients to back off and retry after the rate-limit window.
	CodeRateLimited Code = "RATE_LIMITED"
	// CodeIdempotencyKeyReuse tells clients the Idempotency-Key was already used with a different request body.
	CodeIdempotencyKeyReuse Code = "IDEMPOTENCY_KEY_REUSE"
	// CodeIdempotencyInProgress tells clients a request with this Idempotency-Key is still in flight.
	CodeIdempotencyInProgress Code = "IDEMPOTENCY_IN_PROGRESS"
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
