// Package permissions defines the IBEX Harness 64-bit permission bitmap.
// This is the single source of truth for permission constants.
// See web/content/docs/adr/0009-permission-bitmap.mdx for the full specification.
package permissions

const (
	// Memory operations (bits 0-7).
	MemoryRead       int64 = 1 << 0
	MemoryWrite      int64 = 1 << 1
	MemoryDelete     int64 = 1 << 2
	MemoryBulkExport int64 = 1 << 3

	// Directive operations (bits 8-15).
	DirectiveRead    int64 = 1 << 8
	DirectiveWrite   int64 = 1 << 9
	DirectivePromote int64 = 1 << 10 // requires step-up
	DirectiveRevoke  int64 = 1 << 11 // requires step-up

	// Session operations (bits 16-23).
	SessionCreate        int64 = 1 << 16
	SessionRead          int64 = 1 << 17
	SessionTerminate     int64 = 1 << 18
	OperatorMetadataRead int64 = 1 << 19 // 4.P.1 operator taxonomy

	// Trace operations (bits 24-31).
	TraceRead   int64 = 1 << 24
	TraceExport int64 = 1 << 25

	// Admin operations (bits 32-39).
	UserManage           int64 = 1 << 32
	BillingRead          int64 = 1 << 33
	BillingManage        int64 = 1 << 34
	OrgSettingsWrite     int64 = 1 << 35
	TokenCreate          int64 = 1 << 36
	TokenRevoke          int64 = 1 << 37
	OperatorRedactedRead int64 = 1 << 38
	OperatorRawRead      int64 = 1 << 39 // requires step-up

	// Marketplace + operator actions (bits 40-47).
	MarketplacePublish int64 = 1 << 40
	MarketplaceInstall int64 = 1 << 41
	OperatorExport     int64 = 1 << 42 // requires step-up
	OperatorDelete     int64 = 1 << 43 // requires step-up
	OperatorReplay     int64 = 1 << 44 // requires step-up
	SecretUse          int64 = 1 << 45 // proxy credential get; requires step-up
	PolicyChange       int64 = 1 << 46 // requires step-up
	BreakGlass         int64 = 1 << 47 // requires step-up

	// Federation operations (bits 48-55).
	FederationShare int64 = 1 << 48
	LegalHoldManage int64 = 1 << 49 // requires step-up (4.P.3)
)

// Predefined permission sets.
const (
	// AgentDefault is the minimum permission set for a production agent.
	AgentDefault = MemoryRead | MemoryWrite | SessionCreate | SessionRead | TraceRead

	// ProxyChatCompletion is the minimum required for proxy chat completion (Phase 2).
	// SecretUse is required so GetProviderCredential can resolve BYO/platform keys (4.P.1).
	ProxyChatCompletion = MemoryRead | SessionCreate | SessionRead | SecretUse

	// ReadOnly grants read access to non-admin resources.
	ReadOnly = MemoryRead | DirectiveRead | SessionRead | TraceRead

	// Admin grants all non-federation, non-marketplace permissions in groups 0-39
	// management bits (excludes operator raw/break-glass/secret-use).
	Admin = AgentDefault | DirectiveRead | DirectiveWrite | DirectivePromote |
		DirectiveRevoke | SessionTerminate | TraceExport |
		UserManage | BillingRead | BillingManage | OrgSettingsWrite |
		TokenCreate | TokenRevoke

	// ViewerOperatorDefault is the operator metadata/redacted read set for viewers.
	ViewerOperatorDefault = OperatorMetadataRead | OperatorRedactedRead

	// MemberOperatorDefault matches viewer operator defaults.
	MemberOperatorDefault = ViewerOperatorDefault

	// AdminOperatorDefault adds export + policy-change + legal-hold without raw/secret/break-glass.
	AdminOperatorDefault = MemberOperatorDefault | OperatorExport | PolicyChange | LegalHoldManage
)

// stepUpMask is the set of permissions that require recent TOTP step-up (4.P.1 / 4.P.3).
const stepUpMask = DirectivePromote | DirectiveRevoke |
	OperatorRawRead | OperatorExport | OperatorDelete | OperatorReplay |
	SecretUse | PolicyChange | BreakGlass | LegalHoldManage

// Has returns true if bitmap includes all required permissions.
func Has(bitmap, required int64) bool {
	return bitmap&required == required
}

// HasAny returns true if bitmap includes at least one of the given permissions.
func HasAny(bitmap int64, perms ...int64) bool {
	for _, p := range perms {
		if bitmap&p != 0 {
			return true
		}
	}
	return false
}

// RequiresStepUp returns true if the permission requires TOTP step-up verification.
func RequiresStepUp(permission int64) bool {
	return permission&stepUpMask != 0
}

// RequiresMFA is retained as an alias of RequiresStepUp for ADR-0009 callers.
func RequiresMFA(permission int64) bool {
	return RequiresStepUp(permission)
}

// UsesReservedHighBits reports whether any bit in 56-63 is set.
func UsesReservedHighBits(bitmap int64) bool {
	return uint64(bitmap)>>56 != 0
}
