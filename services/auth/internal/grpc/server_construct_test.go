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
	log := logger.Discard("auth")
	agentSvc, err := service.NewAgentService(agents)
	if err != nil {
		t.Fatalf("NewAgentService: %v", err)
	}

	cases := []struct {
		name string
		deps ServerDeps
	}{
		{name: "nil validator", deps: ServerDeps{
			Validator: nil, TokenService: tokenSvc, AgentService: agentSvc, Metrics: reg, Log: log,
		}},
		{name: "nil token service", deps: ServerDeps{
			Validator: &fakeTokenValidator{}, TokenService: nil, AgentService: agentSvc, Metrics: reg, Log: log,
		}},
		{name: "nil agent service", deps: ServerDeps{
			Validator: &fakeTokenValidator{}, TokenService: tokenSvc, AgentService: nil, Metrics: reg, Log: log,
		}},
		{name: "nil metrics registry", deps: ServerDeps{
			Validator: &fakeTokenValidator{}, TokenService: tokenSvc, AgentService: agentSvc, Metrics: nil, Log: log,
		}},
		{name: "nil log", deps: ServerDeps{
			Validator: &fakeTokenValidator{}, TokenService: tokenSvc, AgentService: agentSvc, Metrics: reg, Log: nil,
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
