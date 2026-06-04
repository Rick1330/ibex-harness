package permissions_test

import (
	"testing"

	"github.com/Rick1330/ibex-harness/packages/permissions"
)

func TestHas(t *testing.T) {
	if !permissions.Has(permissions.AgentDefault, permissions.MemoryRead) {
		t.Fatal("AgentDefault should include MemoryRead")
	}
	if permissions.Has(permissions.AgentDefault, permissions.BillingManage) {
		t.Fatal("AgentDefault must not include BillingManage")
	}
}

func TestHasAny(t *testing.T) {
	if !permissions.HasAny(permissions.ReadOnly, permissions.TraceRead, permissions.TokenCreate) {
		t.Fatal("ReadOnly should match TraceRead")
	}
	if permissions.HasAny(permissions.ReadOnly, permissions.TokenCreate, permissions.BillingManage) {
		t.Fatal("ReadOnly must not match admin-only bits")
	}
}

func TestGroupBitsDoNotOverlap(t *testing.T) {
	groups := []int64{
		permissions.MemoryRead | permissions.MemoryWrite | permissions.MemoryDelete | permissions.MemoryBulkExport,
		permissions.DirectiveRead | permissions.DirectiveWrite | permissions.DirectivePromote | permissions.DirectiveRevoke,
		permissions.SessionCreate | permissions.SessionRead | permissions.SessionTerminate,
		permissions.TraceRead | permissions.TraceExport,
		permissions.UserManage | permissions.BillingRead | permissions.BillingManage |
			permissions.OrgSettingsWrite | permissions.TokenCreate | permissions.TokenRevoke,
		permissions.MarketplacePublish | permissions.MarketplaceInstall,
		permissions.FederationShare,
	}
	for i := 0; i < len(groups); i++ {
		for j := i + 1; j < len(groups); j++ {
			if groups[i]&groups[j] != 0 {
				t.Fatalf("groups %d and %d overlap: %x & %x", i, j, groups[i], groups[j])
			}
		}
	}
}

func TestPredefinedSets(t *testing.T) {
	if permissions.ProxyChatCompletion != (permissions.ProxyChatCompletion & permissions.AgentDefault) {
		t.Fatal("ProxyChatCompletion must be subset of AgentDefault")
	}
	if permissions.AgentDefault != (permissions.AgentDefault & permissions.Admin) {
		t.Fatal("AgentDefault must be subset of Admin")
	}
	if permissions.UsesReservedHighBits(permissions.Admin) {
		t.Fatal("Admin must not use reserved bits 56-63")
	}
}

func TestRequiresMFA(t *testing.T) {
	if !permissions.RequiresMFA(permissions.DirectivePromote) {
		t.Fatal("DirectivePromote requires MFA")
	}
	if permissions.RequiresMFA(permissions.MemoryRead) {
		t.Fatal("MemoryRead must not require MFA")
	}
}

func TestTokenManagementBits(t *testing.T) {
	if !permissions.Has(permissions.Admin, permissions.TokenCreate|permissions.TokenRevoke) {
		t.Fatal("Admin must include token create and revoke")
	}
}
