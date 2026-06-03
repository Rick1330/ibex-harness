package grpcserver

import (
	"context"
	"errors"
	"testing"

	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"github.com/Rick1330/ibex-harness/services/auth/internal/metrics"
	"github.com/Rick1330/ibex-harness/services/auth/internal/token"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

type validateFunc func(context.Context, string) (*authv1.ValidateTokenResponse, error)

type testAuthServer struct {
	authv1.UnimplementedAuthServiceServer
	fn      validateFunc
	metrics *metrics.Metrics
}

func (s *testAuthServer) ValidateToken(ctx context.Context, req *authv1.ValidateTokenRequest) (*authv1.ValidateTokenResponse, error) {
	resp, err := s.fn(ctx, req.GetAccessToken())
	if err != nil {
		if errors.Is(err, token.ErrUnauthenticated) {
			s.metrics.ObserveValidateToken(0, false)
			return nil, status.Error(codes.Unauthenticated, "invalid or expired token")
		}
		s.metrics.ObserveValidateToken(0, false)
		return nil, status.Errorf(codes.Internal, "validation failed")
	}
	s.metrics.ObserveValidateToken(0, true)
	return resp, nil
}

func TestValidateTokenUnauthenticated(t *testing.T) {
	m := metrics.New()
	s := &testAuthServer{
		metrics: m,
		fn: func(context.Context, string) (*authv1.ValidateTokenResponse, error) {
			return nil, token.ErrUnauthenticated
		},
	}
	_, err := s.ValidateToken(context.Background(), &authv1.ValidateTokenRequest{AccessToken: "bad"})
	if status.Code(err) != codes.Unauthenticated {
		t.Fatalf("code: %v", status.Code(err))
	}
}

func TestValidateTokenOK(t *testing.T) {
	m := metrics.New()
	want := &authv1.ValidateTokenResponse{OrgId: "org", Permissions: 7}
	s := &testAuthServer{
		metrics: m,
		fn: func(context.Context, string) (*authv1.ValidateTokenResponse, error) {
			return want, nil
		},
	}
	got, err := s.ValidateToken(context.Background(), &authv1.ValidateTokenRequest{AccessToken: "ok"})
	if err != nil {
		t.Fatalf("err: %v", err)
	}
	if got.GetOrgId() != want.GetOrgId() || got.GetPermissions() != want.GetPermissions() {
		t.Fatalf("response mismatch: %+v", got)
	}
}
