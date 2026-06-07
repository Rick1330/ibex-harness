package metrics

// ValidateToken results for ibex_auth_validate_token_duration_seconds.
const (
	TokenResultOK      = "ok"
	TokenResultError   = "error"
	TokenResultRevoked = "revoked"
)

// ValidateAgent results for ibex_auth_validate_agent_duration_seconds.
const (
	AgentResultOK       = "ok"
	AgentResultError    = "error"
	AgentResultNotFound = "not_found"
)

// RateLimit results for ibex_proxy_rate_limited_total.
const (
	RateLimitAllowed = "allowed"
	RateLimitDenied  = "denied"
)
