package grpcserver

import (
	"testing"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/services/auth/internal/service"
)

func TestUnit_NewServer_RejectsNilDependencies(t *testing.T) {
	t.Parallel()

	tokens := &fakeTokenAPI{}
	agents := &fakeAgentAPI{}
	reg := testAuthRegistry()
	log := logger.Discard("auth")
	var typedNilTokens *service.TokenService
	var typedNilAgents *service.AgentService

	cases := []struct {
		name string
		deps ServerDeps
	}{
		{name: "nil validator", deps: ServerDeps{
			Validator: nil, TokenService: tokens, AgentService: agents, Metrics: reg, Log: log,
		}},
		{name: "nil token service", deps: ServerDeps{
			Validator: &fakeTokenValidator{}, TokenService: nil, AgentService: agents, Metrics: reg, Log: log,
		}},
		{name: "typed-nil token service", deps: ServerDeps{
			Validator: &fakeTokenValidator{}, TokenService: typedNilTokens, AgentService: agents, Metrics: reg, Log: log,
		}},
		{name: "nil agent service", deps: ServerDeps{
			Validator: &fakeTokenValidator{}, TokenService: tokens, AgentService: nil, Metrics: reg, Log: log,
		}},
		{name: "typed-nil agent service", deps: ServerDeps{
			Validator: &fakeTokenValidator{}, TokenService: tokens, AgentService: typedNilAgents, Metrics: reg, Log: log,
		}},
		{name: "nil metrics registry", deps: ServerDeps{
			Validator: &fakeTokenValidator{}, TokenService: tokens, AgentService: agents, Metrics: nil, Log: log,
		}},
		{name: "nil log", deps: ServerDeps{
			Validator: &fakeTokenValidator{}, TokenService: tokens, AgentService: agents, Metrics: reg, Log: nil,
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
