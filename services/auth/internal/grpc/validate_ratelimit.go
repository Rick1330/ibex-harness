package grpcserver

import (
	"context"
	"net"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/ratelimit"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/peer"
	"google.golang.org/grpc/status"
)

const validateTokenFullMethod = "/ibex.auth.v1.AuthService/ValidateToken"

// ValidateRateLimitOpts configures the ValidateToken abuse interceptor.
type ValidateRateLimitOpts struct {
	Limiter ratelimit.KeyedLimiter
	Log     *logger.Logger
}

// ValidateTokenRateLimitInterceptor throttles ValidateToken by peer address.
// Non-ValidateToken methods pass through. Redis failures fail-open with WARN
// (ValidateToken is assumed private-network; dummy Argon2 remains the timing control).
func ValidateTokenRateLimitInterceptor(opts ValidateRateLimitOpts) grpc.UnaryServerInterceptor {
	limiter := opts.Limiter
	if limiter == nil {
		limiter = ratelimit.NoopKeyed()
	}
	log := opts.Log
	return func(ctx context.Context, req any, info *grpc.UnaryServerInfo, handler grpc.UnaryHandler) (any, error) {
		if info.FullMethod != validateTokenFullMethod {
			return handler(ctx, req)
		}
		res, err := limiter.CheckKey(ctx, peerRateLimitKey(ctx))
		if err != nil {
			if log != nil {
				log.WarnCtx(ctx, "ValidateToken rate limit check failed; allowing", "error", err)
			}
			return handler(ctx, req)
		}
		if !res.Allowed {
			return nil, status.Error(codes.ResourceExhausted, "validate token rate limit exceeded")
		}
		return handler(ctx, req)
	}
}

func peerRateLimitKey(ctx context.Context) string {
	p, ok := peer.FromContext(ctx)
	if !ok || p.Addr == nil {
		return "unknown"
	}
	host, _, err := net.SplitHostPort(p.Addr.String())
	if err != nil {
		return p.Addr.String()
	}
	return host
}
