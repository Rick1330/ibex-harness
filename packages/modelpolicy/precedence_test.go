package modelpolicy

import (
	"context"
	"errors"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/google/uuid"
)

// Precedence matrix (ADR-0075): request model → else agent default → policy veto → Registry.For.
func TestPrecedenceMatrix(t *testing.T) {
	t.Parallel()
	const model = "claude-sonnet-4-5"
	org := uuid.New()
	base, err := provider.NewRegistry(testCatalog(model, "gpt-4o"), fakeProvider{models: []string{model, "gpt-4o"}})
	if err != nil {
		t.Fatal(err)
	}

	cases := []struct {
		name          string
		requestModel  string
		agentDefault  string
		policies      []Policy
		wantCandidate string
		wantErr       error
	}{
		{
			name:          "explicit_allow",
			requestModel:  model,
			policies:      []Policy{{Pattern: "claude-*", Allowed: true, Priority: 1}},
			wantCandidate: model,
		},
		{
			name:          "explicit_deny",
			requestModel:  model,
			policies:      []Policy{{Pattern: "claude-*", Allowed: false, Priority: 1}},
			wantCandidate: model,
			wantErr:       ErrModelNotAllowedForOrg,
		},
		{
			name:          "empty_agent_default_allow",
			requestModel:  "",
			agentDefault:  model,
			policies:      []Policy{{Pattern: "claude-*", Allowed: true, Priority: 1}},
			wantCandidate: model,
		},
		{
			name:          "empty_agent_default_deny",
			requestModel:  "  ",
			agentDefault:  model,
			policies:      []Policy{{Pattern: "claude-*", Allowed: false, Priority: 1}},
			wantCandidate: model,
			wantErr:       ErrModelNotAllowedForOrg,
		},
		{
			name:          "no_policy_rows_registry_for",
			requestModel:  "gpt-4o",
			policies:      nil,
			wantCandidate: "gpt-4o",
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			candidate := ResolveCandidateModel(tc.requestModel, AgentDefaults{DefaultModel: tc.agentDefault})
			if candidate != tc.wantCandidate {
				t.Fatalf("candidate=%q want %q", candidate, tc.wantCandidate)
			}
			loader := &fakeLoader{policies: map[uuid.UUID][]Policy{org: tc.policies}}
			cache, err := NewCache(loader, Config{}, NoopMetrics{})
			if err != nil {
				t.Fatal(err)
			}
			reg, err := NewOrgAwareRegistry(base, cache, NoopMetrics{})
			if err != nil {
				t.Fatal(err)
			}
			_, err = reg.ForOrg(context.Background(), org, candidate)
			if tc.wantErr != nil {
				if !errors.Is(err, tc.wantErr) {
					t.Fatalf("err=%v want %v", err, tc.wantErr)
				}
				return
			}
			if err != nil {
				t.Fatalf("unexpected err: %v", err)
			}
		})
	}
}
