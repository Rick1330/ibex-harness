package grpcserver

import (
	"context"
	"errors"
	"fmt"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/services/auth/internal/service"
	dto "github.com/prometheus/client_model/go"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

func TestUnit_MapValidateAgentErr(t *testing.T) {
	t.Parallel()
	cases := []struct {
		name       string
		err        error
		wantCode   codes.Code
		wantMsg    string
		wantResult metrics.AgentValidateResult
	}{
		{
			name:     "missing not_found metric",
			err:      service.ErrAgentNotAuthorized,
			wantCode: codes.PermissionDenied, wantMsg: "agent not found",
			wantResult: metrics.AgentResultNotFound,
		},
		{
			name:     "inactive error metric existence-safe msg",
			err:      service.ErrAgentInactive,
			wantCode: codes.PermissionDenied, wantMsg: "agent not found",
			wantResult: metrics.AgentResultError,
		},
		{
			name:     "canceled",
			err:      fmt.Errorf("%w: %w", service.ErrAgentLookup, context.Canceled),
			wantCode: codes.Canceled, wantMsg: "request canceled",
			wantResult: metrics.AgentResultError,
		},
		{
			name:     "deadline",
			err:      fmt.Errorf("%w: %w", service.ErrAgentLookup, context.DeadlineExceeded),
			wantCode: codes.DeadlineExceeded, wantMsg: "deadline exceeded",
			wantResult: metrics.AgentResultError,
		},
		{
			name:     "lookup",
			err:      fmt.Errorf("%w: %w", service.ErrAgentLookup, errors.New("db down")),
			wantCode: codes.Internal, wantMsg: "agent lookup failed",
			wantResult: metrics.AgentResultError,
		},
	}
	for _, tc := range cases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			reg := testAuthRegistry()
			s := &Server{metrics: reg}
			before := agentResultSampleCount(t, reg, tc.wantResult)
			err := s.mapValidateAgentErr(time.Now(), tc.err)
			st, ok := status.FromError(err)
			if !ok {
				t.Fatalf("not status: %v", err)
			}
			if st.Code() != tc.wantCode || st.Message() != tc.wantMsg {
				t.Fatalf("got %v %q want %v %q", st.Code(), st.Message(), tc.wantCode, tc.wantMsg)
			}
			after := agentResultSampleCount(t, reg, tc.wantResult)
			if after != before+1 {
				t.Fatalf("metric %s count: before=%d after=%d", tc.wantResult, before, after)
			}
		})
	}
}

func agentResultSampleCount(t *testing.T, reg *metrics.AuthRegistry, result metrics.AgentValidateResult) uint64 {
	t.Helper()
	mfs, err := reg.Gatherer().Gather()
	if err != nil {
		t.Fatalf("gather: %v", err)
	}
	for _, mf := range mfs {
		if mf.GetName() != "ibex_auth_validate_agent_duration_seconds" {
			continue
		}
		for _, m := range mf.GetMetric() {
			if metricHasResultLabel(m, string(result)) {
				return m.GetHistogram().GetSampleCount()
			}
		}
	}
	return 0
}

func metricHasResultLabel(m *dto.Metric, want string) bool {
	for _, l := range m.GetLabel() {
		if l.GetName() == "result" && l.GetValue() == want {
			return true
		}
	}
	return false
}
