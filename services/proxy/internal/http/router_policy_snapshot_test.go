package http

import (
	"strings"
	"testing"

	"github.com/Rick1330/ibex-harness/services/proxy/internal/config"
)

func TestUnit_ProtectedRoutesRequirePolicySnapshot(t *testing.T) {
	t.Parallel()
	validator := &mockValidator{}

	cases := []struct {
		name string
		deps RouterDeps
		want bool
	}{
		{name: "no validator", deps: RouterDeps{}, want: false},
		{
			name: "development optional",
			deps: RouterDeps{Config: config.Config{Environment: "development"}, Validator: validator},
			want: false,
		},
		{
			name: "staging requires both",
			deps: RouterDeps{Config: config.Config{Environment: "staging"}, Validator: validator},
			want: true,
		},
		{
			name: "production requires both",
			deps: RouterDeps{Config: config.Config{Environment: "production"}, Validator: validator},
			want: true,
		},
		{
			name: "fetcher alone insufficient",
			deps: RouterDeps{
				Config: config.Config{Environment: "production"}, Validator: validator,
				PolicySnapshotFetcher: &mockPolicyFetcher{},
			},
			want: true,
		},
		{
			name: "verifier alone insufficient",
			deps: RouterDeps{
				Config: config.Config{Environment: "production"}, Validator: validator,
				PolicySnapshotVerifier: newPolicyVerifier(t, policyTestKeyPair(t), "v1", 1),
			},
			want: true,
		},
		{
			name: "production satisfied",
			deps: RouterDeps{
				Config: config.Config{Environment: "production"}, Validator: validator,
				PolicySnapshotFetcher:  &mockPolicyFetcher{},
				PolicySnapshotVerifier: newPolicyVerifier(t, policyTestKeyPair(t), "v1", 1),
			},
			want: false,
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			if got := protectedRoutesRequirePolicySnapshot(tc.deps); got != tc.want {
				t.Fatalf("got %v want %v", got, tc.want)
			}
		})
	}
}

func TestUnit_NewRouter_ProtectedProfilesRequirePolicySnapshot(t *testing.T) {
	t.Parallel()
	for _, environment := range []string{"staging", "production"} {
		t.Run(environment, func(t *testing.T) {
			deps := defaultChatRouterDeps(t)
			deps.Config.Environment = environment
			deps.PolicySnapshotFetcher = nil
			deps.PolicySnapshotVerifier = nil
			if _, err := NewRouter(deps); err == nil || !strings.Contains(err.Error(), "requires policy snapshot fetcher and verifier") {
				t.Fatalf("NewRouter error=%v, want missing policy snapshot failure", err)
			}
		})
	}
}

func TestUnit_ProtectedAuthWrappers_PolicyStage(t *testing.T) {
	t.Parallel()
	wired := protectedRouteDeps{
		policyFetcher:  &mockPolicyFetcher{},
		policyVerifier: newPolicyVerifier(t, policyTestKeyPair(t), "v1", 1),
	}
	_, _, policyMutation, policyRead, _ := protectedAuthWrappers(wired)
	if policyMutation == nil || policyRead == nil {
		t.Fatal("expected policy middlewares when fetcher and verifier are wired")
	}
	_, _, policyMutation, policyRead, _ = protectedAuthWrappers(protectedRouteDeps{})
	if policyMutation != nil || policyRead != nil {
		t.Fatal("expected nil policy middlewares without fetcher/verifier")
	}
}
