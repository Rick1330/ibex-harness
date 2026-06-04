// Package permissions defines the IBEX Harness 64-bit permission bitmap.
// This is the single source of truth for permission constants.
// See docs/adr/ADR-0009-permission-bitmap.md for the full specification.
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
	DirectivePromote int64 = 1 << 10 // requires MFA
	DirectiveRevoke  int64 = 1 << 11 // requires MFA

	// Session operations (bits 16-23).
	SessionCreate    int64 = 1 << 16
	SessionRead      int64 = 1 << 17
	SessionTerminate int64 = 1 << 18

	// Trace operations (bits 24-31).
	TraceRead   int64 = 1 << 24
	TraceExport int64 = 1 << 25

	// Admin operations (bits 32-39).
	UserManage       int64 = 1 << 32
	BillingRead      int64 = 1 << 33
	BillingManage    int64 = 1 << 34
	OrgSettingsWrite int64 = 1 << 35
	TokenCreate      int64 = 1 << 36
	TokenRevoke      int64 = 1 << 37

	// Marketplace operations (bits 40-47).
	MarketplacePublish int64 = 1 << 40
	MarketplaceInstall int64 = 1 << 41

	// Federation operations (bits 48-55).
	FederationShare int64 = 1 << 48
)

// Predefined permission sets.
const (
	// AgentDefault is the minimum permission set for a production agent.
	AgentDefault = MemoryRead | MemoryWrite | SessionCreate | SessionRead | TraceRead

	// ProxyChatCompletion is the minimum required for proxy chat completion (Phase 2).
	ProxyChatCompletion = MemoryRead | SessionCreate | SessionRead

	// ReadOnly grants read access to non-admin resources.
	ReadOnly = MemoryRead | DirectiveRead | SessionRead | TraceRead

	// Admin grants all non-federation, non-marketplace permissions in groups 0-39.
	Admin = AgentDefault | DirectiveRead | DirectiveWrite | DirectivePromote |
		DirectiveRevoke | SessionTerminate | TraceExport |
		UserManage | BillingRead | BillingManage | OrgSettingsWrite |
		TokenCreate | TokenRevoke
)

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

// RequiresMFA returns true if the permission requires MFA verification.
func RequiresMFA(permission int64) bool {
	return permission&(DirectivePromote|DirectiveRevoke) != 0
}

// UsesReservedHighBits reports whether any bit in 56-63 is set.
func UsesReservedHighBits(bitmap int64) bool {
	return uint64(bitmap)>>56 != 0
}
