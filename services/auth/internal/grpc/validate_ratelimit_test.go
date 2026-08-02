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

type interceptorCase struct {
	name       string
	opts       ValidateRateLimitOpts
	fullMethod string
	ctx        context.Context
	wantCode   codes.Code
	wantCall   bool
}

func TestUnit_ValidateTokenRateLimitInterceptor(t *testing.T) {
	t.Parallel()
	for _, tc := range interceptorCases() {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			runInterceptorCase(t, tc)
		})
	}
}

func interceptorCases() []interceptorCase {
	return []interceptorCase{
		{
			name:       "skips_other_methods",
			opts:       ValidateRateLimitOpts{Limiter: stubKeyedLimiter{res: ratelimit.Result{Allowed: false}}},
			fullMethod: "/ibex.auth.v1.AuthService/CreateToken",
			ctx:        context.Background(),
			wantCode:   codes.OK,
			wantCall:   true,
		},
		{
			name:       "denies_when_exceeded",
			opts:       ValidateRateLimitOpts{Limiter: stubKeyedLimiter{res: ratelimit.Result{Allowed: false, Limit: 1}}},
			fullMethod: validateTokenFullMethod,
			ctx:        peerCtx("127.0.0.1", 4242),
			wantCode:   codes.ResourceExhausted,
			wantCall:   false,
		},
		{
			name: "fail_open_on_redis_error",
			opts: ValidateRateLimitOpts{
				Limiter: stubKeyedLimiter{err: errors.New("redis down")},
				Log:     logger.Discard("auth"),
			},
			fullMethod: validateTokenFullMethod,
			ctx:        peerCtx("127.0.0.1", 4242),
			wantCode:   codes.OK,
			wantCall:   true,
		},
		{
			name:       "nil_limiter_uses_noop",
			opts:       ValidateRateLimitOpts{},
			fullMethod: validateTokenFullMethod,
			ctx:        peerCtx("127.0.0.1", 1),
			wantCode:   codes.OK,
			wantCall:   true,
		},
	}
}

func runInterceptorCase(t *testing.T, tc interceptorCase) {
	t.Helper()
	ic := ValidateTokenRateLimitInterceptor(tc.opts)
	called := false
	_, err := ic(tc.ctx, &authv1.ValidateTokenRequest{},
		&grpc.UnaryServerInfo{FullMethod: tc.fullMethod},
		func(ctx context.Context, req any) (any, error) {
			called = true
			return &authv1.ValidateTokenResponse{}, nil
		},
	)
	assertInterceptorOutcome(t, err, called, tc.wantCode, tc.wantCall)
}

func assertInterceptorOutcome(t *testing.T, err error, called bool, wantCode codes.Code, wantCall bool) {
	t.Helper()
	if status.Code(err) != wantCode {
		t.Fatalf("code=%v want %v err=%v", status.Code(err), wantCode, err)
	}
	if called != wantCall {
		t.Fatalf("handler called=%v want %v", called, wantCall)
	}
}

func TestUnit_PeerRateLimitKey(t *testing.T) {
	t.Parallel()
	cases := []struct {
		name string
		ctx  context.Context
		want string
	}{
		{name: "strips_port", ctx: peerCtx("10.1.2.3", 5555), want: "10.1.2.3"},
		{name: "unknown_without_peer", ctx: context.Background(), want: "unknown"},
		{name: "raw_addr_without_port", ctx: rawPeerCtx("unix-socket"), want: "unix-socket"},
	}
	for _, tc := range cases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			if got := peerRateLimitKey(tc.ctx); got != tc.want {
				t.Fatalf("got %q want %q", got, tc.want)
			}
		})
	}
}

type rawAddr struct{ s string }

func (a *rawAddr) Network() string { return "unix" }
func (a *rawAddr) String() string  { return a.s }

func peerCtx(ip string, port int) context.Context {
	return peer.NewContext(context.Background(), &peer.Peer{
		Addr: &net.TCPAddr{IP: net.ParseIP(ip), Port: port},
	})
}

func rawPeerCtx(addr string) context.Context {
	return peer.NewContext(context.Background(), &peer.Peer{Addr: &rawAddr{s: addr}})
}
