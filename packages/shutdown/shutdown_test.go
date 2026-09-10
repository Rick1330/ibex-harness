package shutdown

import (
	"context"
	"errors"
	"io"
	"net"
	"os"
	"sync/atomic"
	"syscall"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/protobuf/types/known/emptypb"
)

func testLogger(t *testing.T) *logger.Logger {
	t.Helper()
	log, err := logger.New(logger.Config{Service: "test", Writer: io.Discard})
	if err != nil {
		t.Fatal(err)
	}
	return log
}

type hangServer interface {
	Block(context.Context, *emptypb.Empty) (*emptypb.Empty, error)
}

type hangImpl struct{}

func (hangImpl) Block(context.Context, *emptypb.Empty) (*emptypb.Empty, error) {
	return nil, errors.New("unused")
}

func TestCoordinator_CleanShutdown(t *testing.T) {
	sigCh := make(chan os.Signal, 1)
	coord := NewWithSignalChan(5*time.Second, testLogger(t), sigCh)
	var order []int
	coord.Register(func(ctx context.Context) error {
		order = append(order, 1)
		return nil
	})
	coord.Register(func(ctx context.Context) error {
		order = append(order, 2)
		return nil
	})

	go func() {
		sigCh <- syscall.SIGTERM
	}()

	if err := coord.Wait(); err != nil {
		t.Fatalf("Wait: %v", err)
	}
	if len(order) != 2 {
		t.Fatalf("handler count: %d", len(order))
	}
	if order[0] != 1 {
		t.Fatalf("first handler: %d", order[0])
	}
	if order[1] != 2 {
		t.Fatalf("second handler: %d", order[1])
	}
}

func TestCoordinator_TimeoutExceeded(t *testing.T) {
	sigCh := make(chan os.Signal, 1)
	coord := NewWithSignalChan(50*time.Millisecond, testLogger(t), sigCh)
	coord.Register(func(ctx context.Context) error {
		select {
		case <-time.After(200 * time.Millisecond):
			return nil
		case <-ctx.Done():
			return ctx.Err()
		}
	})

	go func() {
		sigCh <- syscall.SIGTERM
	}()

	if err := coord.Wait(); err == nil {
		t.Fatal("expected timeout error")
	}
}

func TestCoordinator_HandlerError(t *testing.T) {
	sigCh := make(chan os.Signal, 1)
	coord := NewWithSignalChan(5*time.Second, testLogger(t), sigCh)
	handlerErr := errors.New("close failed")
	var ranSecond atomic.Bool
	coord.Register(func(ctx context.Context) error {
		return handlerErr
	})
	coord.Register(func(ctx context.Context) error {
		ranSecond.Store(true)
		return nil
	})

	go func() {
		sigCh <- syscall.SIGTERM
	}()

	if err := coord.Wait(); err != nil {
		t.Fatalf("Wait: %v", err)
	}
	if !ranSecond.Load() {
		t.Fatal("second handler should run after first handler error")
	}
}

func TestValidateTimeout(t *testing.T) {
	t.Parallel()
	if err := ValidateTimeout(0); err == nil {
		t.Fatal("expected error for zero timeout")
	}
	if err := ValidateTimeout(time.Second); err != nil {
		t.Fatalf("valid timeout: %v", err)
	}
}

func TestCoordinator_NewUsesDefaultSignalChan(t *testing.T) {
	t.Parallel()
	coord := New(5*time.Second, testLogger(t))
	if coord == nil {
		t.Fatal("expected coordinator")
	}
}

func TestGracefulStopGRPC_nilServer(t *testing.T) {
	t.Parallel()

	if err := GracefulStopGRPC(nil, context.Background()); err != nil {
		t.Fatalf("nil server: %v", err)
	}
}

func TestGracefulStopGRPC_forcesStopOnTimeout(t *testing.T) {
	t.Parallel()

	srv := grpc.NewServer() // nosemgrep: go.grpc.security.grpc-server-insecure-connection
	ctx, cancel := context.WithCancel(context.Background())
	cancel()

	if err := GracefulStopGRPC(srv, ctx); err == nil {
		t.Fatal("expected context error")
	}
}

func TestGracefulStopGRPC_completesWhenIdle(t *testing.T) {
	t.Parallel()

	srv := grpc.NewServer() // nosemgrep: go.grpc.security.grpc-server-insecure-connection
	if err := GracefulStopGRPC(srv, context.Background()); err != nil {
		t.Fatalf("idle stop: %v", err)
	}
}

func TestGracefulStopGRPC_returnsAfterDeadlineWithBlockingRPC(t *testing.T) {
	t.Parallel()

	lis, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = lis.Close() })

	entered := make(chan struct{})
	release := make(chan struct{})
	srv := grpc.NewServer() // nosemgrep: go.grpc.security.grpc-server-insecure-connection
	srv.RegisterService(&grpc.ServiceDesc{
		ServiceName: "shutdown.test.Hang",
		HandlerType: (*hangServer)(nil),
		Methods: []grpc.MethodDesc{{
			MethodName: "Block",
			Handler: func(_ any, _ context.Context, dec func(any) error, _ grpc.UnaryServerInterceptor) (any, error) {
				in := new(emptypb.Empty)
				if err := dec(in); err != nil {
					return nil, err
				}
				close(entered)
				// Ignore RPC context cancellation to simulate a stuck handler.
				<-release
				return &emptypb.Empty{}, nil
			},
		}},
	}, hangImpl{})
	go func() { _ = srv.Serve(lis) }()
	t.Cleanup(func() {
		select {
		case <-release:
		default:
			close(release)
		}
		srv.Stop()
	})

	conn, err := grpc.NewClient(
		lis.Addr().String(),
		grpc.WithTransportCredentials(insecure.NewCredentials()), // nosemgrep: go.grpc.security.grpc-client-insecure-connection
	)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = conn.Close() })

	errCh := make(chan error, 1)
	go func() {
		errCh <- conn.Invoke(context.Background(), "/shutdown.test.Hang/Block", &emptypb.Empty{}, &emptypb.Empty{})
	}()
	select {
	case <-entered:
	case <-time.After(2 * time.Second):
		t.Fatal("blocking RPC never entered handler")
	}

	deadline, cancel := context.WithTimeout(context.Background(), 50*time.Millisecond)
	defer cancel()
	started := time.Now()
	err = GracefulStopGRPC(srv, deadline)
	elapsed := time.Since(started)
	if err == nil {
		t.Fatal("expected deadline error")
	}
	if elapsed > 500*time.Millisecond {
		t.Fatalf("shutdown waited too long with stuck RPC: %v", elapsed)
	}
	// Release the stuck handler so the GracefulStop goroutine can finish.
	select {
	case <-release:
	default:
		close(release)
	}
}

func TestCoordinator_SIGINTImmediate(t *testing.T) {
	sigCh := make(chan os.Signal, 1)
	coord := NewWithSignalChan(30*time.Second, testLogger(t), sigCh)
	var start time.Time
	coord.Register(func(ctx context.Context) error {
		start = time.Now()
		if ctx.Err() == nil {
			t.Fatal("expected expired drain context on SIGINT")
		}
		return nil
	})

	go func() {
		sigCh <- syscall.SIGINT
	}()

	if err := coord.Wait(); err != nil {
		t.Fatalf("Wait: %v", err)
	}
	if time.Since(start) > 100*time.Millisecond {
		t.Fatal("SIGINT shutdown should not wait for drain timeout")
	}
}
