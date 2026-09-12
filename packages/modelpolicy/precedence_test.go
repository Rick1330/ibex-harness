package modelpolicy

import (
	"context"
	"errors"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/google/uuid"
)

type precedenceCase struct {
	name          string
	requestModel  string
	agentDefault  string
	policies      []Policy
	wantCandidate string
	wantErr       error
}

func TestPrecedence_ExplicitAllow(t *testing.T) {
	t.Parallel()
	runPrecedenceCase(t, precedenceCase{
		name: "explicit_allow", requestModel: "claude-sonnet-4-5",
		policies:      []Policy{{Pattern: "claude-*", Allowed: true, Priority: 1}},
		wantCandidate: "claude-sonnet-4-5",
	})
}

func TestPrecedence_ExplicitDeny(t *testing.T) {
	t.Parallel()
	runPrecedenceCase(t, precedenceCase{
		name: "explicit_deny", requestModel: "claude-sonnet-4-5",
		policies:      []Policy{{Pattern: "claude-*", Allowed: false, Priority: 1}},
		wantCandidate: "claude-sonnet-4-5",
		wantErr:       ErrModelNotAllowedForOrg,
	})
}

func TestPrecedence_EmptyAgentDefaultAllow(t *testing.T) {
	t.Parallel()
	runPrecedenceCase(t, precedenceCase{
		name: "empty_agent_default_allow", requestModel: "", agentDefault: "claude-sonnet-4-5",
		policies:      []Policy{{Pattern: "claude-*", Allowed: true, Priority: 1}},
		wantCandidate: "claude-sonnet-4-5",
	})
}

func TestPrecedence_EmptyAgentDefaultDeny(t *testing.T) {
	t.Parallel()
	runPrecedenceCase(t, precedenceCase{
		name: "empty_agent_default_deny", requestModel: "  ", agentDefault: "claude-sonnet-4-5",
		policies:      []Policy{{Pattern: "claude-*", Allowed: false, Priority: 1}},
		wantCandidate: "claude-sonnet-4-5",
		wantErr:       ErrModelNotAllowedForOrg,
	})
}

func TestPrecedence_NoPolicyRows(t *testing.T) {
	t.Parallel()
	runPrecedenceCase(t, precedenceCase{
		name: "no_policy_rows", requestModel: "gpt-4o",
		wantCandidate: "gpt-4o",
	})
}

func runPrecedenceCase(t *testing.T, tc precedenceCase) {
	t.Helper()
	const model = "claude-sonnet-4-5"
	org := uuid.New()
	base, err := provider.NewRegistry(
		testCatalog(model, "gpt-4o"),
		fakeProvider{models: []string{model, "gpt-4o"}},
	)
	if err != nil {
		t.Fatal(err)
	}
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
}
