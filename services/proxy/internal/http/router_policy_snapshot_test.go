package http

import (
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
