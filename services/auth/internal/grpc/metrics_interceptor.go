package grpcserver

import (
	"context"
	"strings"

	ibexmetrics "github.com/Rick1330/ibex-harness/packages/metrics"
	"google.golang.org/grpc"
	"google.golang.org/grpc/status"
)

// MetricsUnaryInterceptor records gRPC request outcomes on the auth registry.
func MetricsUnaryInterceptor(reg *ibexmetrics.AuthRegistry) grpc.UnaryServerInterceptor {
	return func(ctx context.Context, req any, info *grpc.UnaryServerInfo, handler grpc.UnaryHandler) (any, error) {
		resp, err := handler(ctx, req)
		reg.IncGRPCRequest(ibexmetrics.GRPCRequestLabels{
			Method: shortGRPCMethod(info.FullMethod),
			Status: status.Code(err).String(),
		})
		return resp, err
	}
}

func shortGRPCMethod(full string) string {
	if i := strings.LastIndex(full, "/"); i >= 0 && i < len(full)-1 {
		return full[i+1:]
	}
	return full
}
