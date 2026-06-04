package validation

// Input validation limits are security controls, not suggestions.
// Changes require an ADR (see ADR-0013).
const (
	MaxRequestBodyBytes    = 1 * 1024 * 1024 // 1 MiB
	MaxMessagesPerRequest  = 1000
	MaxMessageContentBytes = 100 * 1024 // 100 KiB
	MaxModelNameLength     = 256
	MaxChatMaxTokens       = 1_048_576
	MinTemperature         = 0.0
	MaxTemperature         = 2.0
)
