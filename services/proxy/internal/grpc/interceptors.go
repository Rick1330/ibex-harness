package grpc

import (
	"context"

	"github.com/Rick1330/ibex-harness/packages/reqid"
	"google.golang.org/grpc"
	"google.golang.org/grpc/metadata"
)

// RequestIDUnaryInterceptor injects the request ID from ctx into gRPC call metadata.
func RequestIDUnaryInterceptor() grpc.UnaryClientInterceptor {
	return func(
		ctx context.Context,
		method string,
		req, reply any,
		cc *grpc.ClientConn,
		invoker grpc.UnaryInvoker,
		opts ...grpc.CallOption,
	) error {
		if id, ok := reqid.FromContext(ctx); ok {
			ctx = metadata.AppendToOutgoingContext(ctx, reqid.GRPCMetadataKey, id)
		}
		return invoker(ctx, method, req, reply, cc, opts...)
	}
}
