package grpcserver

import (
	"testing"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/services/auth/internal/service"
	"github.com/Rick1330/ibex-harness/services/auth/internal/token"
)

func TestUnit_NewServer_RejectsNilDependencies(t *testing.T) {
	t.Parallel()

	tokenSvc := service.NewTokenService(
		&fakeTokenRepo{},
		token.DefaultArgon2Params(),
		logger.Discard("auth"),
		nil,
	)
	agents := &fakeAgentsStore{}
	reg := testAuthRegistry()

	cases := []struct {
		name string
		deps ServerDeps
	}{
		{name: "nil validator", deps: ServerDeps{
			Validator: nil, TokenService: tokenSvc, AgentsStore: agents, Metrics: reg,
		}},
		{name: "nil token service", deps: ServerDeps{
			Validator: &fakeTokenValidator{}, TokenService: nil, AgentsStore: agents, Metrics: reg,
		}},
		{name: "nil agents store", deps: ServerDeps{
			Validator: &fakeTokenValidator{}, TokenService: tokenSvc, AgentsStore: nil, Metrics: reg,
		}},
		{name: "nil metrics registry", deps: ServerDeps{
			Validator: &fakeTokenValidator{}, TokenService: tokenSvc, AgentsStore: agents, Metrics: nil,
		}},
	}

	for _, tc := range cases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			_, err := NewServer(tc.deps)
			if err == nil {
				t.Fatal("expected constructor error")
			}
		})
	}
}
