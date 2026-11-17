//go:build integration

package repository_test

import (
	"testing"

	"github.com/Rick1330/ibex-harness/services/auth/internal/repository"
)

// agentsLookupCase is one scenario for TestAgentsRepository_GetByIDAndOrg.
type agentsLookupCase struct {
	name       string
	status     string
	crossOrg   bool
	wantNil    bool
	wantStatus string
}

// assertRecord checks the lookup result against the case: a cross-org lookup
// must return nil, and an in-org lookup must return the seeded agent.
func (tc agentsLookupCase) assertRecord(t *testing.T, s agentsScenario, rec *repository.AgentRecord) {
	t.Helper()
	if tc.wantNil {
		if rec != nil {
			t.Fatalf("expected nil for cross-org lookup, got %+v", rec)
		}
		return
	}
	if rec == nil {
		t.Fatal("expected agent record")
	}
	if rec.ID != s.AgentID {
		t.Fatalf("id: %s", rec.ID)
	}
	if rec.OrgID != s.OrgA {
		t.Fatalf("org: %s", rec.OrgID)
	}
	if rec.Status != tc.wantStatus {
		t.Fatalf("status: %s", rec.Status)
	}
}

func TestAgentsRepository_GetByIDAndOrg(t *testing.T) {
	tests := []agentsLookupCase{
		{name: "active agent", status: "active", wantStatus: "active"},
		{name: "wrong org returns nil", status: "active", crossOrg: true, wantNil: true},
		{name: "paused agent", status: "paused", wantStatus: "paused"},
	}

	for _, tc := range tests {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			withAgentsScenario(t, tc.status, tc.crossOrg, func(t *testing.T, s agentsScenario, lookupOrg string) {
				tc.assertRecord(t, s, s.lookupAgent(t, lookupOrg))
			})
		})
	}
}
