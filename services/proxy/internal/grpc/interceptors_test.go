package grpc_test

import (
	"context"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/reqid"
	proxygrpc "github.com/Rick1330/ibex-harness/services/proxy/internal/grpc"
	"google.golang.org/grpc"
	"google.golang.org/grpc/metadata"
)

func TestRequestIDUnaryInterceptor_propagatesMetadata(t *testing.T) {
	const wantID = "550e8400-e29b-41d4-a716-446655440000"
	ctx := reqid.WithRequestID(context.Background(), wantID)

	var gotMD metadata.MD
	interceptor := proxygrpc.RequestIDUnaryInterceptor()
	err := interceptor(ctx, "/test.Method", nil, nil, nil, func(
		callCtx context.Context,
		_ string,
		_, _ any,
		_ *grpc.ClientConn,
		_ ...grpc.CallOption,
	) error {
		gotMD, _ = metadata.FromOutgoingContext(callCtx)
		return nil
	}, grpc.EmptyCallOption{})
	if err != nil {
		t.Fatal(err)
	}
	vals := gotMD.Get(reqid.GRPCMetadataKey)
	if len(vals) != 1 || vals[0] != wantID {
		t.Fatalf("metadata: %v want %q", vals, wantID)
	}
}

func TestRequestIDUnaryInterceptor_skipsWhenMissing(t *testing.T) {
	interceptor := proxygrpc.RequestIDUnaryInterceptor()
	err := interceptor(context.Background(), "/test.Method", nil, nil, nil, func(
		callCtx context.Context,
		_ string,
		_, _ any,
		_ *grpc.ClientConn,
		_ ...grpc.CallOption,
	) error {
		md, ok := metadata.FromOutgoingContext(callCtx)
		if ok && len(md.Get(reqid.GRPCMetadataKey)) > 0 {
			t.Fatal("unexpected request id metadata")
		}
		return nil
	}, grpc.EmptyCallOption{})
	if err != nil {
		t.Fatal(err)
	}
}
