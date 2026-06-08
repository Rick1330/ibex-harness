package metrics

// TokenValidateResult labels ibex_auth_validate_token_duration_seconds.
type TokenValidateResult string

// AgentValidateResult labels ibex_auth_validate_agent_duration_seconds.
type AgentValidateResult string

// DBOperation labels ibex_db_query_duration_seconds.
type DBOperation string

// GRPCRequestLabels labels ibex_auth_grpc_requests_total.
type GRPCRequestLabels struct {
	Method string
	Status string
}

// ValidateTokenObservation records ValidateToken duration.
type ValidateTokenObservation struct {
	Result  TokenValidateResult
	Seconds float64
}

// ValidateAgentObservation records ValidateAgent duration.
type ValidateAgentObservation struct {
	Result  AgentValidateResult
	Seconds float64
}

// DBQueryObservation records database query duration.
type DBQueryObservation struct {
	Operation DBOperation
	Seconds   float64
}

// DB operation names for ibex_db_query_duration_seconds.
const (
	DBOpFindTokenByPrefix DBOperation = "find_token_by_prefix"
	DBOpCreateToken       DBOperation = "create_token"
	DBOpRevokeToken       DBOperation = "revoke_token"
	DBOpListTokens        DBOperation = "list_tokens"
	DBOpGetAgentByID      DBOperation = "get_agent_by_id"
)

// ValidateToken results for ibex_auth_validate_token_duration_seconds.
const (
	TokenResultOK      TokenValidateResult = "ok"
	TokenResultError   TokenValidateResult = "error"
	TokenResultRevoked TokenValidateResult = "revoked"
)

// ValidateAgent results for ibex_auth_validate_agent_duration_seconds.
const (
	AgentResultOK       AgentValidateResult = "ok"
	AgentResultError    AgentValidateResult = "error"
	AgentResultNotFound AgentValidateResult = "not_found"
)
