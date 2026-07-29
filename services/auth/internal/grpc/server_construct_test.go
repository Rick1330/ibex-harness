package grpcserver

import (
	"testing"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/metrics"
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
		name      string
		validator tokenValidator
		tokenSvc  *service.TokenService
		agents    AgentStore
		reg       *metrics.AuthRegistry
	}{
		{name: "nil validator", validator: nil, tokenSvc: tokenSvc, agents: agents, reg: reg},
		{name: "nil token service", validator: &fakeTokenValidator{}, tokenSvc: nil, agents: agents, reg: reg},
		{name: "nil agents store", validator: &fakeTokenValidator{}, tokenSvc: tokenSvc, agents: nil, reg: reg},
		{name: "nil metrics registry", validator: &fakeTokenValidator{}, tokenSvc: tokenSvc, agents: agents, reg: nil},
	}

	for _, tc := range cases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			_, err := NewServer(tc.validator, tc.tokenSvc, tc.agents, tc.reg)
			if err == nil {
				t.Fatal("expected constructor error")
			}
		})
	}
}
