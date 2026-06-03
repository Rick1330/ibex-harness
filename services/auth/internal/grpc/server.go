package grpcserver

import (
	"context"
	"errors"
	"time"

	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"github.com/Rick1330/ibex-harness/services/auth/internal/metrics"
	"github.com/Rick1330/ibex-harness/services/auth/internal/token"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

// Server implements AuthService.ValidateToken.
type Server struct {
	authv1.UnimplementedAuthServiceServer
	validator *token.Validator
	metrics   *metrics.Metrics
}

func NewServer(validator *token.Validator, m *metrics.Metrics) *Server {
	return &Server{validator: validator, metrics: m}
}

func (s *Server) ValidateToken(ctx context.Context, req *authv1.ValidateTokenRequest) (*authv1.ValidateTokenResponse, error) {
	start := time.Now()
	resp, err := s.validator.Validate(ctx, req.GetAccessToken())
	elapsed := time.Since(start).Seconds()

	if err != nil {
		if errors.Is(err, token.ErrUnauthenticated) {
			s.metrics.ObserveValidateToken(elapsed, false)
			return nil, status.Error(codes.Unauthenticated, "invalid or expired token")
		}
		s.metrics.ObserveValidateToken(elapsed, false)
		return nil, status.Errorf(codes.Internal, "validation failed")
	}
	s.metrics.ObserveValidateToken(elapsed, true)
	return resp, nil
}
