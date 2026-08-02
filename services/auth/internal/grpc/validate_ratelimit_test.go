package grpcserver

import (
	"context"
	"errors"
	"net"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/logger"
	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"github.com/Rick1330/ibex-harness/packages/ratelimit"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/peer"
	"google.golang.org/grpc/status"
)

type stubKeyedLimiter struct {
	res ratelimit.Result
	err error
}

func (s stubKeyedLimiter) CheckKey(_ context.Context, _ string) (ratelimit.Result, error) {
	return s.res, s.err
}

func TestValidateTokenRateLimitInterceptor_skipsOtherMethods(t *testing.T) {
	t.Parallel()
	ic := ValidateTokenRateLimitInterceptor(ValidateRateLimitOpts{
		Limiter: stubKeyedLimiter{res: ratelimit.Result{Allowed: false}},
	})
	called := false
	_, err := ic(context.Background(), &authv1.CreateTokenRequest{},
		&grpc.UnaryServerInfo{FullMethod: "/ibex.auth.v1.AuthService/CreateToken"},
		func(ctx context.Context, req any) (any, error) {
			called = true
			return &authv1.CreateTokenResponse{}, nil
		},
	)
	if err != nil || !called {
		t.Fatalf("err=%v called=%v", err, called)
	}
}

func TestValidateTokenRateLimitInterceptor_deniesWhenExceeded(t *testing.T) {
	t.Parallel()
	ic := ValidateTokenRateLimitInterceptor(ValidateRateLimitOpts{
		Limiter: stubKeyedLimiter{res: ratelimit.Result{Allowed: false, Limit: 1}},
	})
	_, err := ic(peerCtx("127.0.0.1", 4242), &authv1.ValidateTokenRequest{},
		&grpc.UnaryServerInfo{FullMethod: validateTokenFullMethod},
		func(ctx context.Context, req any) (any, error) {
			t.Fatal("handler should not run")
			return nil, nil
		},
	)
	if status.Code(err) != codes.ResourceExhausted {
		t.Fatalf("code=%v err=%v", status.Code(err), err)
	}
}

func TestValidateTokenRateLimitInterceptor_failOpenOnRedisError(t *testing.T) {
	t.Parallel()
	ic := ValidateTokenRateLimitInterceptor(ValidateRateLimitOpts{
		Limiter: stubKeyedLimiter{err: errors.New("redis down")},
		Log:     logger.Discard("auth"),
	})
	called := false
	_, err := ic(peerCtx("127.0.0.1", 4242), &authv1.ValidateTokenRequest{},
		&grpc.UnaryServerInfo{FullMethod: validateTokenFullMethod},
		func(ctx context.Context, req any) (any, error) {
			called = true
			return &authv1.ValidateTokenResponse{}, nil
		},
	)
	if err != nil || !called {
		t.Fatalf("fail-open expected; err=%v called=%v", err, called)
	}
}

func TestPeerRateLimitKey_stripsPort(t *testing.T) {
	t.Parallel()
	got := peerRateLimitKey(peerCtx("10.1.2.3", 5555))
	if got != "10.1.2.3" {
		t.Fatalf("got %q", got)
	}
}

func peerCtx(ip string, port int) context.Context {
	return peer.NewContext(context.Background(), &peer.Peer{
		Addr: &net.TCPAddr{IP: net.ParseIP(ip), Port: port},
	})
}
