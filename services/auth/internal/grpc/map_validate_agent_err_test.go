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
			name:     "inactive error metric suspended msg",
			err:      service.ErrAgentInactive,
			wantCode: codes.PermissionDenied, wantMsg: "agent is not active",
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
			assertStatusCodeMsg(t, st, tc.wantCode, tc.wantMsg)
			after := agentResultSampleCount(t, reg, tc.wantResult)
			if after != before+1 {
				t.Fatalf("metric %s count: before=%d after=%d", tc.wantResult, before, after)
			}
		})
	}
}

func assertStatusCodeMsg(t *testing.T, st *status.Status, wantCode codes.Code, wantMsg string) {
	t.Helper()
	if st.Code() != wantCode {
		t.Fatalf("code=%v want %v", st.Code(), wantCode)
	}
	if st.Message() != wantMsg {
		t.Fatalf("msg=%q want %q", st.Message(), wantMsg)
	}
}

func agentResultSampleCount(t *testing.T, reg *metrics.AuthRegistry, result metrics.AgentValidateResult) uint64 {
	t.Helper()
	mfs, err := reg.Gatherer().Gather()
	if err != nil {
		t.Fatalf("gather: %v", err)
	}
	mf := findValidateAgentDurationFamily(mfs)
	if mf == nil {
		return 0
	}
	return sampleCountForAgentResult(mf, string(result))
}

func findValidateAgentDurationFamily(mfs []*dto.MetricFamily) *dto.MetricFamily {
	for _, mf := range mfs {
		if mf.GetName() == "ibex_auth_validate_agent_duration_seconds" {
			return mf
		}
	}
	return nil
}

func sampleCountForAgentResult(mf *dto.MetricFamily, wantResult string) uint64 {
	for _, m := range mf.GetMetric() {
		if metricHasResultLabel(m, wantResult) {
			return m.GetHistogram().GetSampleCount()
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
